"""
api/routes/connections.py
──────────────────────────
ERP tool connection management.

Endpoints:
  GET  /connections/              — list all tool connections for this company
  POST /connections/tranzact      — save TranzAct credentials (encrypted)
  POST /connections/tranzact/test — test connectivity with stored credentials
  DELETE /connections/{tool_name} — remove a connection

Credential storage:
  Credentials are AES-256 encrypted via Fernet before writing to DB.
  The encryption key lives in FERNET_KEY env var (32-byte URL-safe base64).
  Bearer tokens are NEVER persisted — they live only in the in-memory cache
  in adapters/tranzact/auth.py.

Multi-ERP design:
  The tool_connections table has a `source` column (e.g., 'tranzact', 'tally').
  Adding a new ERP = new row in tool_connections + new adapter module.
  No schema migration needed.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import date, timedelta
from typing import Optional

import psycopg2
import psycopg2.errors
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from vinayak.config import DATABASE_URL, TRANZACT_BASE_URL
from vinayak.api.routes.auth import get_current_user, TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Full-sync orchestration (initial data pull after connecting) ──────────────
# A single background worker runs all 10 pipelines once, in rate-limit-safe
# order. State is process-local; the frontend polls /dashboard/sync/health to
# render progress.
_sync_lock = threading.Lock()
_sync_state = {
    "running": False,
    "started_at": None,
    "finished_at": None,
    "error": None,
    "total": 0,
    "completed": 0,
    "current": None,
    "pipelines": [],   # [{"key", "label", "status", "rows", "error"}]
}


def _full_sync_plan():
    """(PipelineClass, from_days_back, key, label) for every pipeline, ordered
    fast→slow so operational panels light up first."""
    from vinayak.pipelines.ar_aging import ARAgingPipeline
    from vinayak.pipelines.sales_orders import SalesOrdersPipeline
    from vinayak.pipelines.purchase_orders import PurchaseOrdersPipeline
    from vinayak.pipelines.inventory_valuation import InventoryValuationPipeline
    from vinayak.pipelines.process_details import ProcessDetailsPipeline
    from vinayak.pipelines.sales_invoices import SalesInvoicesPipeline
    from vinayak.pipelines.purchase_invoices import PurchaseInvoicesPipeline
    from vinayak.pipelines.grn_qir import GRNQIRPipeline
    from vinayak.pipelines.sales_quotations import SalesQuotationsPipeline
    from vinayak.pipelines.process_routing import ProcessRoutingPipeline

    # Initial sync window: 1 month for every pipeline. The dashboard shows the
    # most recent month immediately; older history is filled in afterwards by
    # the nightly backward-backfill job (vinayak/jobs/backfill.py) or on demand
    # via POST /connections/tranzact/history.
    INITIAL_WINDOW_DAYS = 30
    return [
        (ARAgingPipeline, INITIAL_WINDOW_DAYS, "ar_aging", "AR Aging"),
        (SalesOrdersPipeline, INITIAL_WINDOW_DAYS, "sales_orders", "Sales Orders"),
        (PurchaseOrdersPipeline, INITIAL_WINDOW_DAYS, "purchase_orders", "Purchase Orders"),
        (InventoryValuationPipeline, INITIAL_WINDOW_DAYS, "inventory_valuation", "Inventory Valuation"),
        (ProcessDetailsPipeline, INITIAL_WINDOW_DAYS, "process_details", "Production Details"),
        (SalesInvoicesPipeline, INITIAL_WINDOW_DAYS, "sales_invoices", "Sales Invoices"),
        (PurchaseInvoicesPipeline, INITIAL_WINDOW_DAYS, "purchase_invoices", "Purchase Invoices"),
        (GRNQIRPipeline, INITIAL_WINDOW_DAYS, "grn_qir", "GRN / Quality"),
        (SalesQuotationsPipeline, INITIAL_WINDOW_DAYS, "sales_quotations", "Sales Quotations"),
        (ProcessRoutingPipeline, INITIAL_WINDOW_DAYS, "process_routing", "Process Routing"),
    ]


def _run_full_sync(email: str, password: str) -> None:
    """Prime the token cache with the user's stored credentials, then run
    every pipeline once.  For each pipeline the window is computed as:

      • First ever run  → today minus the default days_back window
      • Subsequent runs → last successful completed_at date (with 1-day
                          overlap to catch late-arriving records), capped at
                          the default window so we never regress too far back.

    Per-pipeline failures are logged (recorded in tz_sync_runs by BasePipeline)
    but never abort the whole run."""
    global _sync_state
    import datetime as _dt
    plan = _full_sync_plan()

    # Seed the per-pipeline checklist up front so the UI can render all rows.
    with _sync_lock:
        _sync_state["total"] = len(plan)
        _sync_state["completed"] = 0
        _sync_state["current"] = None
        _sync_state["pipelines"] = [
            {"key": key, "label": label, "status": "pending", "rows": None, "error": None}
            for _, _, key, label in plan
        ]

    def _set(key, **fields):
        with _sync_lock:
            for p in _sync_state["pipelines"]:
                if p["key"] == key:
                    p.update(fields)
                    break

    def _incremental_from(PipelineCls, days_back: int, today: date) -> date:
        """Return the from_date for an incremental run.

        Uses the last successful sync date (minus 1 day overlap) when available,
        otherwise falls back to the full default window.
        """
        default_from = today - timedelta(days=days_back)
        try:
            db = psycopg2.connect(DATABASE_URL)
            try:
                last = PipelineCls.get_last_success_date(db)
            finally:
                db.close()
            if last is not None:
                # Re-fetch from 1 day before last success to cover edge cases,
                # but never go further back than the default window.
                incremental = max(last - timedelta(days=1), default_from)
                logger.info(
                    "%s: incremental sync from %s (last success: %s)",
                    PipelineCls.PIPELINE_NAME, incremental, last,
                )
                return incremental
        except Exception as exc:
            logger.warning("Could not query last sync date for %s: %s", PipelineCls.__name__, exc)
        return default_from

    try:
        # Prime the in-memory token cache using the credentials the user just
        # connected with, so the whole sync is driven by THEIR account.
        from vinayak.adapters.tranzact.auth import get_access_token
        get_access_token(
            base_url=TRANZACT_BASE_URL,
            email=email,
            password=password,
            force_refresh=True,
        )
        today = date.today()
        for PipelineCls, days_back, key, _label in plan:
            with _sync_lock:
                _sync_state["current"] = key
            _set(key, status="running")
            try:
                from_date = _incremental_from(PipelineCls, days_back, today)
                rows = PipelineCls().run(from_date, today)
                _set(key, status="success", rows=rows)
            except Exception as exc:  # noqa: BLE001
                logger.error("Full sync: %s failed: %s", PipelineCls.__name__, exc)
                _set(key, status="failed", error=str(exc))
            finally:
                with _sync_lock:
                    _sync_state["completed"] += 1
    except Exception as exc:  # noqa: BLE001
        logger.error("Full sync aborted: %s", exc)
        with _sync_lock:
            _sync_state["error"] = str(exc)
    finally:
        with _sync_lock:
            _sync_state["running"] = False
            _sync_state["current"] = None
            _sync_state["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()

# ── Fernet encryption ─────────────────────────────────────────────────────────
_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is not None:
        return _fernet
    key = os.environ.get("FERNET_KEY", "")
    if not key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="FERNET_KEY not configured — cannot store credentials",
        )
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode())
        return _fernet
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fernet init failed: {exc}",
        )


def _encrypt(data: dict) -> str:
    f = _get_fernet()
    return f.encrypt(json.dumps(data).encode()).decode()


def _decrypt(blob: str) -> dict:
    f = _get_fernet()
    return json.loads(f.decrypt(blob.encode()).decode())


# ── DB helper ─────────────────────────────────────────────────────────────────
def _conn():
    return psycopg2.connect(DATABASE_URL)


def _raise_if_schema_missing(exc: Exception) -> None:
    """Convert UndefinedTable → a readable 503 with setup instructions."""
    msg = str(exc)
    if "UndefinedTable" in type(exc).__name__ or "does not exist" in msg:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Database schema not initialised. "
                "Run: python -m vinayak.scripts.setup_db"
            ),
        )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Database error: {exc}",
    )


# ── Schemas ───────────────────────────────────────────────────────────────────
class TranzActCredentials(BaseModel):
    email: str
    password: str


# ── Routes ────────────────────────────────────────────────────────────────────
@router.get("/", summary="List all tool connections for this company")
def list_connections(user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT tool_name, connection_method, is_active,
                       last_verified_at, created_at
                FROM tool_connections
                WHERE company_id = %s
                ORDER BY created_at
                """,
                (user.company_id,),
            )
            rows = cur.fetchall()
    except Exception as exc:
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    return {
        "connections": [
            {
                "tool_name":        r[0],
                "connection_method": r[1],
                "is_active":        r[2],
                "last_verified_at": r[3].isoformat() if r[3] else None,
                "created_at":       r[4].isoformat() if r[4] else None,
            }
            for r in rows
        ]
    }


@router.post("/tranzact", summary="Save TranzAct credentials (encrypted)")
def save_tranzact(
    creds: TranzActCredentials,
    user: TokenPayload = Depends(get_current_user),
):
    """
    Encrypts email+password and upserts into tool_connections.
    The encryption key (FERNET_KEY) never leaves the server.
    Bearer tokens are NOT stored here — they're fetched on demand.
    """
    encrypted = _encrypt({"email": creds.email, "password": creds.password})

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tool_connections
                    (company_id, tool_name, connection_method, encrypted_credentials, is_active)
                VALUES (%s, 'tranzact', 'cloud_pull', %s, TRUE)
                ON CONFLICT (company_id, tool_name)
                DO UPDATE SET
                    encrypted_credentials = EXCLUDED.encrypted_credentials,
                    is_active             = TRUE,
                    updated_at            = NOW()
                """,
                (user.company_id, encrypted),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    logger.info("Saved TranzAct credentials for company %s", user.company_id)
    return {"status": "ok", "tool_name": "tranzact", "message": "Credentials saved"}


@router.post("/tranzact/test", summary="Test TranzAct auth with stored credentials")
def test_tranzact(user: TokenPayload = Depends(get_current_user)):
    """
    Decrypts stored credentials and attempts a TranzAct login.
    Returns ok=True if the bearer token was obtained successfully.
    Does NOT expose the token — only confirms connectivity.
    """
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT encrypted_credentials FROM tool_connections
                WHERE company_id = %s AND tool_name = 'tranzact' AND is_active = TRUE
                """,
                (user.company_id,),
            )
            row = cur.fetchone()
    except Exception as exc:
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No TranzAct credentials found. Connect TranzAct first.",
        )

    creds = _decrypt(row[0])

    try:
        from vinayak.adapters.tranzact.auth import get_access_token
        token = get_access_token(
            base_url=TRANZACT_BASE_URL,
            email=creds["email"],
            password=creds["password"],
            force_refresh=True,
        )
        # Update last_verified_at
        db = _conn()
        try:
            with db.cursor() as cur:
                cur.execute(
                    """UPDATE tool_connections
                       SET last_verified_at = NOW()
                       WHERE company_id = %s AND tool_name = 'tranzact'""",
                    (user.company_id,),
                )
            db.commit()
        finally:
            db.close()

        # Return only the first 12 chars of the token as proof — never the full token
        return {
            "ok": True,
            "tool_name": "tranzact",
            "token_preview": token[:12] + "...",
            "message": "Authentication successful",
        }
    except Exception as exc:
        logger.warning("TranzAct test failed for %s: %s", user.company_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TranzAct authentication failed: {exc}",
        )


@router.post("/tranzact/sync", summary="Run the initial full data sync (all pipelines)")
def trigger_full_sync(user: TokenPayload = Depends(get_current_user)):
    """
    Kick off a one-time pull of all 10 TranzAct reports into the cache tables,
    using the stored (encrypted) credentials. Runs in a background thread and
    returns immediately — poll GET /dashboard/sync/health for progress.
    """
    global _sync_state
    with _sync_lock:
        if _sync_state["running"]:
            return {"status": "already_running", "started_at": _sync_state["started_at"]}

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT encrypted_credentials FROM tool_connections
                WHERE company_id = %s AND tool_name = 'tranzact' AND is_active = TRUE
                """,
                (user.company_id,),
            )
            row = cur.fetchone()
    except Exception as exc:
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No TranzAct credentials found. Connect TranzAct first.",
        )

    creds = _decrypt(row[0])

    import datetime as _dt
    with _sync_lock:
        _sync_state.update(
            running=True,
            started_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            finished_at=None,
            error=None,
        )

    threading.Thread(
        target=_run_full_sync,
        args=(creds["email"], creds["password"]),
        daemon=True,
    ).start()

    logger.info("Full sync started for company %s", user.company_id)
    return {"status": "started", "pipeline_count": 10}


@router.get("/tranzact/sync", summary="Full-sync progress state")
def full_sync_status(user: TokenPayload = Depends(get_current_user)):
    with _sync_lock:
        return dict(_sync_state)


# ── On-demand history backfill ───────────────────────────────────────────────
# Lets a user reach further into the past than the initial 1-month window.
# Runs the same backward-backfill step the nightly cron uses, in a background
# thread. Process-local guard prevents overlapping backfills per process.
_backfill_lock = threading.Lock()
_backfill_running = False


class HistoryBackfillRequest(BaseModel):
    months: int = 1        # how many extra months of history to pull this call
    floor_months: int = 12  # don't go further back than this many months total


@router.post("/tranzact/history", summary="Pull older history (backward backfill)")
def trigger_history_backfill(
    body: HistoryBackfillRequest | None = None,
    user: TokenPayload = Depends(get_current_user),
):
    """
    Walk each pipeline's history one (or more) months further into the past,
    on top of whatever has already been fetched. Returns immediately; the work
    runs in a background thread. Safe to call repeatedly — it advances the
    backfill watermark and stops once the floor is reached.
    """
    global _backfill_running
    req = body or HistoryBackfillRequest()

    with _backfill_lock:
        if _backfill_running:
            return {"status": "already_running"}

    # Load this company's stored credentials.
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT encrypted_credentials FROM tool_connections
                    WHERE company_id = %s AND tool_name = 'tranzact' AND is_active = TRUE""",
                (user.company_id,),
            )
            row = cur.fetchone()
    except Exception as exc:
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No TranzAct credentials found. Connect TranzAct first.",
        )

    creds = _decrypt(row[0])

    def _worker(company_id: str, email: str, password: str, months: int, floor_months: int):
        global _backfill_running
        try:
            from vinayak.jobs.backfill import backfill_company
            summary = backfill_company(
                company_id, email, password, months=months, floor_months=floor_months,
            )
            logger.info("History backfill done for %s: %s", company_id, summary)
        except Exception as exc:  # noqa: BLE001
            logger.error("History backfill failed for %s: %s", company_id, exc)
        finally:
            with _backfill_lock:
                _backfill_running = False

    with _backfill_lock:
        _backfill_running = True

    threading.Thread(
        target=_worker,
        args=(user.company_id, creds["email"], creds["password"], req.months, req.floor_months),
        daemon=True,
    ).start()

    logger.info("History backfill started for company %s (+%d months)", user.company_id, req.months)
    return {"status": "started", "months": req.months, "floor_months": req.floor_months}


@router.get("/tranzact/history", summary="History backfill state + coverage")
def history_backfill_status(user: TokenPayload = Depends(get_current_user)):
    """Report whether a backfill is running and how far back each pipeline goes."""
    from vinayak.api.routes.connections import _full_sync_plan  # self-import safe

    conn = _conn()
    coverage = []
    try:
        for PipelineCls, _d, key, label in _full_sync_plan():
            try:
                oldest = PipelineCls.get_oldest_fetched_date(conn, user.company_id)
            except Exception:
                oldest = None
            coverage.append({
                "key": key,
                "label": label,
                "oldest_fetched_date": oldest.isoformat() if oldest else None,
            })
    finally:
        conn.close()

    with _backfill_lock:
        running = _backfill_running
    return {"running": running, "coverage": coverage}


@router.delete("/{tool_name}", summary="Remove a tool connection")
def delete_connection(
    tool_name: str,
    user: TokenPayload = Depends(get_current_user),
):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE tool_connections
                   SET is_active = FALSE, updated_at = NOW()
                   WHERE company_id = %s AND tool_name = %s""",
                (user.company_id, tool_name),
            )
            deleted = cur.rowcount
        conn.commit()
    finally:
        conn.close()

    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active connection found for tool '{tool_name}'",
        )

    return {"status": "ok", "tool_name": tool_name, "message": "Connection removed"}
