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
from vinayak.api.routes.workspaces import require_workspace

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Full-sync orchestration (initial data pull after connecting) ──────────────
# Per-company sync state so brand A's sync never leaks into brand B's status.
# Each company gets its own lock + state dict created on first use.
_sync_states: dict[str, dict] = {}
_sync_locks:  dict[str, threading.Lock] = {}
_sync_meta_lock = threading.Lock()  # guards the dicts themselves


def _company_sync(company_id: str) -> tuple[threading.Lock, dict]:
    """Return (lock, state) for this company, creating them if needed."""
    with _sync_meta_lock:
        if company_id not in _sync_states:
            _sync_locks[company_id] = threading.Lock()
            _sync_states[company_id] = {
                "running":     False,
                "started_at":  None,
                "finished_at": None,
                "error":       None,
                "total":       0,
                "completed":   0,
                "current":     None,
                "pipelines":   [],
            }
        return _sync_locks[company_id], _sync_states[company_id]


# Hard time limit per report. A report either finishes fetching its window
# within PIPELINE_FETCH_TIMEOUT seconds, or it is abandoned and flagged so the
# sync can never run endlessly. Two layers enforce it:
#   • max_seconds — fetch_report stops paging once this elapses (cooperative).
#   • a thread-join backstop (PIPELINE_HARD_TIMEOUT) — even if a single request
#     hangs below the socket timeout or a step blocks outside the page loop, the
#     orchestrator stops waiting and moves on, marking the report 'timed_out'.
PIPELINE_FETCH_TIMEOUT = 90
PIPELINE_HARD_TIMEOUT = PIPELINE_FETCH_TIMEOUT + 20  # grace for in-flight request


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


def _run_full_sync(email: str, password: str, company_id: str) -> None:
    """Run every pipeline once for this company.  State is scoped to
    company_id so two brands can sync concurrently without clobbering."""
    import datetime as _dt
    lock, state = _company_sync(company_id)
    plan = _full_sync_plan()

    with lock:
        state["total"]     = len(plan)
        state["completed"] = 0
        state["current"]   = None
        state["pipelines"] = [
            {"key": key, "label": label, "status": "pending", "rows": None, "error": None}
            for _, _, key, label in plan
        ]

    def _set(key, **fields):
        with lock:
            for p in state["pipelines"]:
                if p["key"] == key:
                    p.update(fields)
                    break

    def _incremental_from(PipelineCls, days_back: int, today: date) -> date:
        default_from = today - timedelta(days=days_back)
        try:
            db = psycopg2.connect(DATABASE_URL)
            try:
                last = PipelineCls.get_last_success_date(db, company_id)
            finally:
                db.close()
            if last is not None:
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
        from vinayak.adapters.tranzact.client import TranzactCreds
        creds = TranzactCreds(email=email, password=password, base_url=TRANZACT_BASE_URL)
        today = date.today()
        for PipelineCls, days_back, key, _label in plan:
            with lock:
                state["current"] = key
            _set(key, status="running")

            # Run the report in a worker thread so a hung fetch can't stall the
            # whole sync — we wait at most PIPELINE_HARD_TIMEOUT, then move on.
            holder: dict = {"rows": None, "error": None}

            def _work(PipelineCls=PipelineCls, days_back=days_back, holder=holder):
                try:
                    from_date = _incremental_from(PipelineCls, days_back, today)
                    holder["rows"] = PipelineCls().run(
                        from_date, today,
                        company_id=company_id,
                        max_seconds=PIPELINE_FETCH_TIMEOUT,
                        creds=creds,
                    )
                except Exception as exc:  # noqa: BLE001
                    holder["error"] = str(exc)

            worker = threading.Thread(target=_work, daemon=True)
            worker.start()
            worker.join(PIPELINE_HARD_TIMEOUT)

            if worker.is_alive():
                logger.error(
                    "Full sync: %s exceeded %ds — abandoned (timed_out)",
                    PipelineCls.__name__, PIPELINE_FETCH_TIMEOUT,
                )
                _set(key, status="timed_out",
                     error=f"Report took longer than {PIPELINE_FETCH_TIMEOUT}s and was stopped.")
            elif holder["error"]:
                logger.error("Full sync: %s failed: %s", PipelineCls.__name__, holder["error"])
                _set(key, status="failed", error=holder["error"])
            else:
                _set(key, status="success", rows=holder["rows"])

            with lock:
                state["completed"] += 1

        # Layer 0: map the freshly-synced tz_* rows into the canonical schema so
        # the dashboard (which now reads canon_*) reflects the new data. Failures
        # here don't fail the sync — the canonical layer just lags one cycle.
        try:
            from vinayak.canonical.tranzact_canonical import rebuild_canonical
            cdb = psycopg2.connect(DATABASE_URL)
            try:
                stats = rebuild_canonical(cdb, company_id)
                logger.info("Canonical rebuild for %s: %s", company_id, stats.upserted)
            finally:
                cdb.close()
        except Exception as exc:  # noqa: BLE001
            logger.error("Canonical rebuild failed for %s: %s", company_id, exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Full sync aborted for %s: %s", company_id, exc)
        with lock:
            state["error"] = str(exc)
    finally:
        with lock:
            state["running"]     = False
            state["current"]     = None
            state["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()

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
def list_connections(company_id: str = Depends(require_workspace)):
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
                (company_id,),
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
    company_id: str = Depends(require_workspace),
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
                (company_id, encrypted),
            )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    logger.info("Saved TranzAct credentials for company %s", company_id)
    return {"status": "ok", "tool_name": "tranzact", "message": "Credentials saved"}


@router.post("/tranzact/test", summary="Test TranzAct auth with stored credentials")
def test_tranzact(company_id: str = Depends(require_workspace)):
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
                (company_id,),
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
                    (company_id,),
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
        logger.warning("TranzAct test failed for %s: %s", company_id, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"TranzAct authentication failed: {exc}",
        )


@router.post("/tranzact/sync", summary="Run the initial full data sync (all pipelines)")
def trigger_full_sync(company_id: str = Depends(require_workspace)):
    """
    Kick off a one-time pull of all 10 TranzAct reports into the cache tables,
    using the stored (encrypted) credentials. Runs in a background thread and
    returns immediately — poll GET /dashboard/sync/health for progress.
    """
    lock, state = _company_sync(company_id)
    with lock:
        if state["running"]:
            return {"status": "already_running", "started_at": state["started_at"]}

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT encrypted_credentials FROM tool_connections
                WHERE company_id = %s AND tool_name = 'tranzact' AND is_active = TRUE
                """,
                (company_id,),
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
    with lock:
        state.update(
            running=True,
            started_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
            finished_at=None,
            error=None,
        )

    threading.Thread(
        target=_run_full_sync,
        args=(creds["email"], creds["password"], company_id),
        daemon=True,
    ).start()

    logger.info("Full sync started for company %s", company_id)
    return {"status": "started", "pipeline_count": 10}


@router.get("/tranzact/sync", summary="Full-sync progress state")
def full_sync_status(company_id: str = Depends(require_workspace)):
    lock, state = _company_sync(company_id)
    with lock:
        return dict(state)


# ── On-demand history backfill ───────────────────────────────────────────────
# Per-company backfill state (mirrors the per-company sync state above).
_backfill_locks:   dict[str, threading.Lock] = {}
_backfill_running: dict[str, bool] = {}
_backfill_meta_lock = threading.Lock()


def _company_backfill(company_id: str) -> tuple[threading.Lock, dict]:
    """Return (lock, running_cell) — running_cell is a 1-element list so the
    worker thread can mutate it by reference."""
    with _backfill_meta_lock:
        if company_id not in _backfill_locks:
            _backfill_locks[company_id] = threading.Lock()
            _backfill_running[company_id] = False
        return _backfill_locks[company_id], _backfill_running


class HistoryBackfillRequest(BaseModel):
    months: int = 1        # how many extra months of history to pull this call
    floor_months: int = 12  # don't go further back than this many months total


@router.post("/tranzact/history", summary="Pull older history (backward backfill)")
def trigger_history_backfill(
    body: HistoryBackfillRequest | None = None,
    company_id: str = Depends(require_workspace),
):
    """
    Walk each pipeline's history one (or more) months further into the past,
    on top of whatever has already been fetched. Returns immediately; the work
    runs in a background thread. Safe to call repeatedly — it advances the
    backfill watermark and stops once the floor is reached.
    """
    req = body or HistoryBackfillRequest()
    bf_lock, bf_map = _company_backfill(company_id)

    with bf_lock:
        if bf_map[company_id]:
            return {"status": "already_running"}

    # Load this company's stored credentials.
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT encrypted_credentials FROM tool_connections
                    WHERE company_id = %s AND tool_name = 'tranzact' AND is_active = TRUE""",
                (company_id,),
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

    def _worker(cid: str, email: str, password: str, months: int, floor_months: int):
        bl, bm = _company_backfill(cid)
        try:
            from vinayak.jobs.backfill import backfill_company
            summary = backfill_company(
                cid, email, password, months=months, floor_months=floor_months,
            )
            logger.info("History backfill done for %s: %s", cid, summary)
        except Exception as exc:  # noqa: BLE001
            logger.error("History backfill failed for %s: %s", cid, exc)
        finally:
            with bl:
                bm[cid] = False

    with bf_lock:
        bf_map[company_id] = True

    threading.Thread(
        target=_worker,
        args=(company_id, creds["email"], creds["password"], req.months, req.floor_months),
        daemon=True,
    ).start()

    logger.info("History backfill started for company %s (+%d months)", company_id, req.months)
    return {"status": "started", "months": req.months, "floor_months": req.floor_months}


@router.get("/tranzact/history", summary="History backfill state + coverage")
def history_backfill_status(company_id: str = Depends(require_workspace)):
    """Report whether a backfill is running and how far back each pipeline goes."""
    from vinayak.api.routes.connections import _full_sync_plan  # self-import safe

    conn = _conn()
    coverage = []
    try:
        for PipelineCls, _d, key, label in _full_sync_plan():
            try:
                oldest = PipelineCls.get_oldest_fetched_date(conn, company_id)
            except Exception:
                oldest = None
            coverage.append({
                "key": key,
                "label": label,
                "oldest_fetched_date": oldest.isoformat() if oldest else None,
            })
    finally:
        conn.close()

    bf_lock, bf_map = _company_backfill(company_id)
    with bf_lock:
        running = bf_map.get(company_id, False)
    return {"running": running, "coverage": coverage}


@router.delete("/{tool_name}", summary="Remove a tool connection")
def delete_connection(
    tool_name: str,
    company_id: str = Depends(require_workspace),
):
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE tool_connections
                   SET is_active = FALSE, updated_at = NOW()
                   WHERE company_id = %s AND tool_name = %s""",
                (company_id, tool_name),
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
