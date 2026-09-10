"""
api/routes/milestones.py
─────────────────────────
The evidence surface for the contractual milestones (docs/reference/MILESTONES.md):

  GET  /dashboard/usage/me                — my active days and qualifying-week runs
  GET  /dashboard/usage/users             — everyone seen in this workspace (owner/admin)
  GET  /dashboard/experiments             — list (optionally by status)
  POST /dashboard/experiments             — create (manual or ai_suggested)
  GET  /dashboard/experiments/counts      — the Milestone-1 numbers
  PATCH/dashboard/experiments/{id}        — update fields / transition status
  GET  /dashboard/incidents · POST · PATCH

Everything is scoped to the workspace like every other route; the users list
is limited to owner/admin roles.

The milestone BOARD used to live here as a screen. It does not any more: the
tracker is docs/reference/MILESTONES.md, because a milestone review is a
conversation with Shourya and Sandeep and a document can hold what a table
cannot — what was agreed, what changed, and why a criterion is judged the way
it is. The countable half is computed by vinayak/milestones.py and printed by
`python -m vinayak.scripts.milestone_status` for pasting into that document.
The evidence tables underneath (usage_events, experiments, incidents,
eval_runs) are unchanged and still recorded automatically.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from vinayak import experiments as X
from vinayak import usage as U
from vinayak.api.deps import get_db as _conn, get_current_user, require_workspace, TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter()

MANAGER_ROLES = ("owner", "admin")


# ── helpers ───────────────────────────────────────────────────────────────────
_BLANK_USER = {"role": None, "may_approve_messages": False, "may_approve_money": False,
               "pinned_cards": None, "display_name": None}


def user_record(conn, email: str) -> dict:
    """The users row as the app sees it (role + permissions + layout).

    The permission and layout columns arrived in migration 020. On a database
    where that migration has not been run yet this must degrade to "no role
    chosen" rather than throwing — a failed SELECT aborts the transaction, and
    a caller that catches the error still inherits a dead connection. That is
    exactly how a missing migration used to turn into a blank Today page.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT email, company_id, role, may_approve_messages, may_approve_money,
                          pinned_cards, display_name
                   FROM users WHERE LOWER(email) = LOWER(%s)""", (email,))
            r = cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — most likely migration 020 is not applied
        conn.rollback()
        logger.warning("user_record: falling back for %s (%s)", email, exc)
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT email, company_id, role FROM users "
                            "WHERE LOWER(email) = LOWER(%s)", (email,))
                r2 = cur.fetchone()
            if r2:
                return {**_BLANK_USER, "email": r2[0], "company_id": r2[1], "role": r2[2]}
        except Exception:  # noqa: BLE001
            conn.rollback()
        return {**_BLANK_USER, "email": email}
    if not r:
        return {**_BLANK_USER, "email": email}
    return {"email": r[0], "company_id": r[1], "role": r[2],
            "may_approve_messages": bool(r[3]), "may_approve_money": bool(r[4]),
            "pinned_cards": r[5], "display_name": r[6]}


def _require_manager(conn, user: TokenPayload) -> dict:
    rec = user_record(conn, user.sub)
    if rec.get("role") not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Owner or admin role required")
    return rec


# ── usage ─────────────────────────────────────────────────────────────────────
@router.get("/usage/me")
def usage_me(window_days: int = Query(default=120, ge=7, le=400),
             company_id: str = Depends(require_workspace),
             user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        return U.stats(conn, user.sub, window_days=window_days)
    finally:
        conn.close()


@router.get("/usage/users")
def usage_users(window_days: int = Query(default=120, ge=7, le=400),
                company_id: str = Depends(require_workspace),
                user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        _require_manager(conn, user)
        return {"users": U.users_seen(conn, company_id, window_days)}
    finally:
        conn.close()


# ── experiments ───────────────────────────────────────────────────────────────
class ExperimentIn(BaseModel):
    title: str
    hypothesis: str | None = None
    source: str = "manual"
    metric: str | None = None
    baseline: float | None = None
    target: float | None = None
    action_refs: list | None = None
    evidence: dict | None = None
    started_at: str | None = None
    ends_at: str | None = None
    status: str = "proposed"


class ExperimentPatch(BaseModel):
    title: str | None = None
    hypothesis: str | None = None
    metric: str | None = None
    baseline: float | None = None
    target: float | None = None
    result: float | None = None
    outcome: str | None = None
    outcome_notes: str | None = None
    action_refs: list | None = None
    evidence: dict | None = None
    started_at: str | None = None
    ends_at: str | None = None
    status: str | None = None


@router.get("/experiments")
def experiments_list(status: str | None = Query(default=None),
                     company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"experiments": X.list_for(conn, company_id, status=status),
                "counts": X.counts(conn, company_id)}
    finally:
        conn.close()


@router.get("/experiments/counts")
def experiments_counts(company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return X.counts(conn, company_id)
    finally:
        conn.close()


@router.post("/experiments")
def experiments_create(body: ExperimentIn, company_id: str = Depends(require_workspace),
                       user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        try:
            exp = X.create(conn, company_id, proposed_by=user.sub,
                           **body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"experiment": exp}
    finally:
        conn.close()


@router.patch("/experiments/{experiment_id}")
def experiments_update(experiment_id: str, body: ExperimentPatch,
                       company_id: str = Depends(require_workspace),
                       user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        try:
            exp = X.update(conn, company_id, experiment_id,
                           body.model_dump(exclude_none=True), by=user.sub)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if exp is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        return {"experiment": exp}
    finally:
        conn.close()


# ── incidents ─────────────────────────────────────────────────────────────────
class IncidentIn(BaseModel):
    severity: str          # critical | major | minor
    title: str
    detail: str | None = None
    started_at: str | None = None


class IncidentPatch(BaseModel):
    resolved: bool | None = None
    detail: str | None = None
    severity: str | None = None


_SEVERITIES = ("critical", "major", "minor")


def _incident_rows(conn, company_id: str, limit: int = 100) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, company_id, severity, title, detail, started_at, resolved_at, reported_by
               FROM incidents WHERE company_id = %s OR company_id IS NULL
               ORDER BY started_at DESC LIMIT %s""", (company_id, limit))
        rows = cur.fetchall()
    return [{"id": str(r[0]), "company_id": r[1], "severity": r[2], "title": r[3], "detail": r[4],
             "started_at": r[5].isoformat() if r[5] else None,
             "resolved_at": r[6].isoformat() if r[6] else None, "reported_by": r[7]} for r in rows]


@router.get("/incidents")
def incidents_list(company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"incidents": _incident_rows(conn, company_id)}
    finally:
        conn.close()


@router.post("/incidents")
def incidents_create(body: IncidentIn, company_id: str = Depends(require_workspace),
                     user: TokenPayload = Depends(get_current_user)):
    if body.severity not in _SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity must be one of {_SEVERITIES}")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO incidents (company_id, severity, title, detail, started_at, reported_by)
                   VALUES (%s, %s, %s, %s, COALESCE(%s::timestamptz, NOW()), %s) RETURNING id""",
                (company_id, body.severity, body.title.strip(), body.detail, body.started_at, user.sub))
            new_id = str(cur.fetchone()[0])
        conn.commit()
        return {"id": new_id}
    finally:
        conn.close()


@router.patch("/incidents/{incident_id}")
def incidents_update(incident_id: str, body: IncidentPatch,
                     company_id: str = Depends(require_workspace)):
    if body.severity is not None and body.severity not in _SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity must be one of {_SEVERITIES}")
    conn = _conn()
    try:
        sets, params = [], []
        if body.resolved is True:
            sets.append("resolved_at = COALESCE(resolved_at, NOW())")
        if body.resolved is False:
            sets.append("resolved_at = NULL")
        if body.detail is not None:
            sets.append("detail = %s"); params.append(body.detail)
        if body.severity is not None:
            sets.append("severity = %s"); params.append(body.severity)
        if not sets:
            return {"ok": True}
        with conn.cursor() as cur:
            cur.execute(f"UPDATE incidents SET {', '.join(sets)} WHERE id = %s AND (company_id = %s OR company_id IS NULL)",
                        (*params, incident_id, company_id))
            n = cur.rowcount
        conn.commit()
        if not n:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"ok": True}
    finally:
        conn.close()
