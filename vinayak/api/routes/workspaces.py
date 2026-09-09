"""
api/routes/workspaces.py
─────────────────────────
Workspace (brand) management + the require_workspace dependency.

A "workspace" is one brand = one TranzAct account = one data scope. It is the
`companies` row whose id is used as `company_id` across every tz_ table. One
owner owns many workspaces (single-owner mode: a workspace with owner_id IS NULL
belongs to the configured admin).

The browser tab is pinned to a workspace via the URL (`/w/{brand}/…`); the BFF
forwards that brand as the `X-Workspace-Id` header. `require_workspace` reads
that header, verifies the logged-in owner may access the brand, and returns the
company_id every query/sync should scope to. When the header is absent it falls
back to the JWT's default company_id (single-brand compatibility).

Endpoints:
  GET  /workspaces        — list brands the owner can open
  POST /workspaces        — create a new brand (workspace)
"""
from __future__ import annotations

import logging
import re

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from vinayak.config import DATABASE_URL
from vinayak.api.routes.auth import get_current_user, TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter()

WORKSPACE_HEADER = "X-Workspace-Id"
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,48}$")


from vinayak.db.session import db as _db


def _conn():
    return _db.connect()


def _owns_clause(user: TokenPayload) -> tuple[str, tuple]:
    """SQL predicate (and params) for 'workspaces this owner can access'.

    Global admin (company_id not set in JWT) → sees all companies.
    Regular user → sees companies where owner_id matches their email,
    plus any company with owner_id IS NULL (shared/unowned brands).
    """
    if not user.company_id or user.company_id == "":
        return "TRUE", ()
    return "(owner_id IS NULL OR owner_id = %s)", (user.sub,)


def require_workspace(
    request: Request,
    user: TokenPayload = Depends(get_current_user),
) -> str:
    """FastAPI dependency — resolve + authorise the active workspace.

    Returns the company_id to scope queries/syncs by. Raises 403 if the owner
    has no access to the requested brand, 404 if the brand does not exist.
    """
    ws = request.headers.get(WORKSPACE_HEADER) or user.company_id
    clause, params = _owns_clause(user)

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT 1 FROM companies WHERE id = %s AND {clause}",
                (ws, *params),
            )
            ok = cur.fetchone()
        if ok:
            # Usage evidence (Milestone 1): one row per user per workspace per
            # day. Best-effort and cached in-process; never blocks a request.
            from vinayak import usage as _usage
            _usage.record(conn, ws, user.sub)
    finally:
        conn.close()

    if not ok:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"No access to workspace '{ws}'",
        )
    return ws


# ── Users of a workspace (roles + approval permissions) ───────────────────────
class UserPermIn(BaseModel):
    email: str
    role: str | None = None
    may_approve_messages: bool | None = None
    may_approve_money: bool | None = None


def _require_manager(conn, user: TokenPayload) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT role FROM users WHERE LOWER(email) = LOWER(%s)", (user.sub,))
        r = cur.fetchone()
    if not r or r[0] not in ("owner", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Owner or admin role required")


@router.get("/users", summary="Users who can open this workspace, with roles and permissions")
def list_users(company_id: str = Depends(require_workspace),
               user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        _require_manager(conn, user)
        with conn.cursor() as cur:
            cur.execute(
                """SELECT email, role, may_approve_messages, may_approve_money, display_name, company_id
                   FROM users WHERE company_id = %s OR company_id IS NULL ORDER BY email""",
                (company_id,))
            rows = cur.fetchall()
    finally:
        conn.close()
    return {"users": [{"email": r[0], "role": r[1], "may_approve_messages": bool(r[2]),
                       "may_approve_money": bool(r[3]), "display_name": r[4],
                       "global_admin": r[5] is None} for r in rows]}


@router.put("/users", summary="Set a user's role and approval permissions (owner/admin)")
def put_user(body: UserPermIn, company_id: str = Depends(require_workspace),
             user: TokenPayload = Depends(get_current_user)):
    from vinayak.api.routes.auth import ROLES
    sets, params = [], []
    if body.role is not None:
        if body.role not in ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of {ROLES}")
        sets.append("role = %s"); params.append(body.role)
    if body.may_approve_messages is not None:
        sets.append("may_approve_messages = %s"); params.append(body.may_approve_messages)
    if body.may_approve_money is not None:
        sets.append("may_approve_money = %s"); params.append(body.may_approve_money)
    if not sets:
        return {"ok": True}
    conn = _conn()
    try:
        _require_manager(conn, user)
        with conn.cursor() as cur:
            cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE LOWER(email) = LOWER(%s) AND (company_id = %s OR company_id IS NULL)",
                        (*params, body.email, company_id))
            n = cur.rowcount
        conn.commit()
    finally:
        conn.close()
    if not n:
        raise HTTPException(status_code=404, detail="No such user in this workspace")
    return {"ok": True}


# ── Schemas ───────────────────────────────────────────────────────────────────
class CreateWorkspaceRequest(BaseModel):
    id: str    # url-safe brand slug, e.g. "protegere"
    name: str  # display name, e.g. "Protegere"


# ── Routes ────────────────────────────────────────────────────────────────────
@router.get("/", summary="List workspaces (brands) the owner can open")
def list_workspaces(user: TokenPayload = Depends(get_current_user)):
    clause, params = _owns_clause(user)
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT c.id, c.name,
                       EXISTS (
                           SELECT 1 FROM tool_connections t
                           WHERE t.company_id = c.id
                             AND t.tool_name = 'tranzact'
                             AND t.is_active = TRUE
                       ) AS connected
                FROM companies c
                WHERE {clause}
                ORDER BY c.created_at
                """,
                params,
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    return {
        "workspaces": [
            {"id": r[0], "name": r[1], "connected": bool(r[2])}
            for r in rows
        ]
    }


@router.post("/", summary="Create a new workspace (brand)")
def create_workspace(
    body: CreateWorkspaceRequest,
    user: TokenPayload = Depends(get_current_user),
):
    slug = body.id.strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace id must be 2-49 chars: lowercase letters, digits, - or _",
        )

    conn = _conn()
    try:
        with conn.cursor() as cur:
            # Reject collisions with a brand the owner cannot see (someone
            # else's), but allow re-creating one's own as a no-op.
            cur.execute("SELECT owner_id FROM companies WHERE id = %s", (slug,))
            existing = cur.fetchone()
            if existing is not None:
                owner = existing[0]
                if owner is not None and owner != user.sub:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Workspace '{slug}' already exists",
                    )
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Workspace '{slug}' already exists",
                )

            cur.execute(
                "INSERT INTO companies (id, name, owner_id) VALUES (%s, %s, %s)",
                (slug, body.name.strip(), user.sub),
            )
        conn.commit()
    except HTTPException:
        conn.rollback()
        conn.close()
        raise
    except Exception as exc:
        conn.rollback()
        conn.close()
        logger.error("create_workspace failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not create workspace: {exc}",
        )
    finally:
        if not conn.closed:
            conn.close()

    logger.info("Created workspace %s (%s) for owner %s", slug, body.name, user.sub)
    return {"status": "ok", "id": slug, "name": body.name.strip()}
