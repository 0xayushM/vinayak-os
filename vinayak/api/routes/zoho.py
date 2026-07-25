"""
api/routes/zoho.py
───────────────────
The /zoho namespace — connection management and sync for the Zoho Books source.
Mirror of the TranzAct connection flow: credentials are Fernet-encrypted into
tool_connections (tool_name='zoho_books'), never returned by any endpoint.

Endpoints (all workspace-scoped, behind the BFF + internal key):
  POST   /zoho/connect      store creds after a live test against the Zoho API
  GET    /zoho/status       connection state + recent sync runs
  POST   /zoho/sync         run all four Zoho pipelines for this workspace
  DELETE /zoho/connect      deactivate the connection (creds retained, inactive)
"""
from __future__ import annotations

import logging

import psycopg2
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from vinayak.api.routes.auth import TokenPayload, get_current_user  # noqa: F401 (scoping dep)
from vinayak.api.routes.connections import _decrypt, _encrypt
from vinayak.api.routes.workspaces import require_workspace
from vinayak.adapters.zoho.auth import DCS, ZohoCreds
from vinayak.adapters.zoho.client import test_connection
from vinayak.config import DATABASE_URL

logger = logging.getLogger(__name__)
router = APIRouter()

TOOL_NAME = "zoho_books"


class ZohoConnectIn(BaseModel):
    client_id: str
    client_secret: str
    refresh_token: str
    organization_id: str
    dc: str = "in"


def _conn():
    return psycopg2.connect(DATABASE_URL)


def _load_creds(conn, company_id: str) -> ZohoCreds:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT encrypted_credentials FROM tool_connections
               WHERE company_id=%s AND tool_name=%s AND is_active=TRUE""",
            (company_id, TOOL_NAME),
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, detail="No active Zoho Books connection for this workspace.")
    d = _decrypt(row[0])
    return ZohoCreds(client_id=d["client_id"], client_secret=d["client_secret"],
                     refresh_token=d["refresh_token"],
                     organization_id=d["organization_id"], dc=d.get("dc", "in"))


@router.post("/connect")
def zoho_connect(body: ZohoConnectIn, company_id: str = Depends(require_workspace)):
    """Validate the credentials against the live Zoho API, then store encrypted."""
    if body.dc not in DCS:
        raise HTTPException(400, detail=f"dc must be one of {sorted(DCS)}")
    creds = ZohoCreds(**body.model_dump())
    try:
        org = test_connection(creds)   # raises on bad token / wrong org / wrong DC
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, detail=f"Zoho connection test failed: {exc}")

    blob = _encrypt(body.model_dump())
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tool_connections
                       (company_id, tool_name, connection_method, encrypted_credentials,
                        is_active, last_verified_at)
                   VALUES (%s, %s, 'oauth_refresh_token', %s, TRUE, NOW())
                   ON CONFLICT (company_id, tool_name) DO UPDATE SET
                       encrypted_credentials = EXCLUDED.encrypted_credentials,
                       connection_method     = EXCLUDED.connection_method,
                       is_active = TRUE, last_verified_at = NOW(), updated_at = NOW()""",
                (company_id, TOOL_NAME, blob),
            )
        conn.commit()
    finally:
        conn.close()
    logger.info("Zoho Books connected for %s (org=%s)", company_id, org.get("name"))
    return {"status": "connected", "organization": org}


@router.get("/status")
def zoho_status(company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT is_active, last_verified_at FROM tool_connections
                   WHERE company_id=%s AND tool_name=%s""",
                (company_id, TOOL_NAME),
            )
            row = cur.fetchone()
            cur.execute(
                """SELECT pipeline_name, status, started_at, rows_upserted,
                          LEFT(COALESCE(error_message,''),200)
                   FROM tz_sync_runs
                   WHERE company_id=%s AND pipeline_name LIKE 'zoho_%%'
                   ORDER BY started_at DESC LIMIT 8""",
                (company_id,),
            )
            runs = [{"pipeline": r[0], "status": r[1],
                     "started_at": r[2].isoformat() if r[2] else None,
                     "rows_upserted": r[3], "error": r[4] or None}
                    for r in cur.fetchall()]
    finally:
        conn.close()
    return {"connected": bool(row and row[0]),
            "last_verified_at": row[1].isoformat() if row and row[1] else None,
            "recent_runs": runs}


@router.post("/sync")
def zoho_sync(company_id: str = Depends(require_workspace)):
    """Run all four Zoho pipelines now (synchronous — Zoho orgs are small at
    our stage; move to background when a big org shows up)."""
    from vinayak.pipelines.zoho import ALL_ZOHO_PIPELINES

    conn = _conn()
    try:
        creds = _load_creds(conn, company_id)
    finally:
        conn.close()

    results, failures = {}, 0
    for PipelineCls in ALL_ZOHO_PIPELINES:
        p = PipelineCls()
        try:
            results[p.PIPELINE_NAME] = p.run(company_id, creds)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            results[p.PIPELINE_NAME] = {"error": str(exc)[:300]}

    # Rebuild the canonical layer from the freshly-synced zb_* rows so the
    # dashboard/AI (which read canon_* only) reflect the new data. Never let a
    # canonical failure mask a successful sync.
    canonical = None
    try:
        from vinayak.canonical.zoho_canonical import rebuild_canonical_zoho
        cdb = _conn()
        try:
            stats = rebuild_canonical_zoho(cdb, company_id)
            canonical = stats.upserted
        finally:
            cdb.close()
    except Exception as exc:  # noqa: BLE001
        logger.exception("zoho canonical rebuild failed for %s", company_id)
        canonical = {"error": str(exc)[:300]}

    return {"status": "partial" if failures else "ok",
            "results": results, "canonical": canonical}


@router.delete("/connect")
def zoho_disconnect(company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE tool_connections SET is_active=FALSE, updated_at=NOW()
                   WHERE company_id=%s AND tool_name=%s""",
                (company_id, TOOL_NAME),
            )
        conn.commit()
    finally:
        conn.close()
    return {"status": "disconnected"}
