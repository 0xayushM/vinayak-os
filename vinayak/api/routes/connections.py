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
    """(PipelineClass, key, label) for every pipeline, ordered fast→slow so
    operational panels light up first. Every run fetches the complete report —
    TranzAct has no usable server-side date filter."""
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

    return [
        (ARAgingPipeline, "ar_aging", "AR Aging"),
        (SalesOrdersPipeline, "sales_orders", "Sales Orders"),
        (PurchaseOrdersPipeline, "purchase_orders", "Purchase Orders"),
        (InventoryValuationPipeline, "inventory_valuation", "Inventory Valuation"),
        (ProcessDetailsPipeline, "process_details", "Production Details"),
        (SalesInvoicesPipeline, "sales_invoices", "Sales Invoices"),
        (PurchaseInvoicesPipeline, "purchase_invoices", "Purchase Invoices"),
        (GRNQIRPipeline, "grn_qir", "GRN / Quality"),
        (SalesQuotationsPipeline, "sales_quotations", "Sales Quotations"),
        (ProcessRoutingPipeline, "process_routing", "Process Routing"),
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
            for _, key, label in plan
        ]

    def _set(key, **fields):
        with lock:
            for p in state["pipelines"]:
                if p["key"] == key:
                    p.update(fields)
                    break

    try:
        from vinayak.adapters.tranzact.client import TranzactCreds
        creds = TranzactCreds(email=email, password=password, base_url=TRANZACT_BASE_URL)
        for PipelineCls, key, _label in plan:
            with lock:
                state["current"] = key
            _set(key, status="running")

            # Run the report in a worker thread so a hung fetch can't stall the
            # whole sync — we wait at most PIPELINE_HARD_TIMEOUT, then move on.
            holder: dict = {"rows": None, "error": None}

            def _work(PipelineCls=PipelineCls, holder=holder):
                try:
                    holder["rows"] = PipelineCls().run(
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


# ── Per-API resumable migration ───────────────────────────────────────────────
# Each report can be migrated on its own from Settings. TranzAct has no usable
# server-side date filter, so a large history is pulled by WALKING PAGES. A
# persistent cursor (tz_sync_cursor) records how far each report has paged, so a
# run resumes the REMAINING pages instead of re-fetching the whole report — and
# a long migration survives a process restart. See docs/RESUMABLE_SYNC.md.
#
# The walk runs in a background thread (the user never waits) and persists the
# cursor + rebuilds the canonical layer after every chunk, so the dashboard
# fills in progressively.
CHUNK_PAGES = 10          # pages fetched per chunk (~75s at the rate limit)
REFRESH_PAGES = 4         # pages pulled on a routine refresh of a complete report
CHUNK_MAX_SECONDS = 150   # per-chunk wall-clock safety cap

_pipeline_states: dict[str, dict] = {}        # company_id -> {key -> transient run state}
_pipeline_locks:  dict[str, threading.Lock] = {}
_pipeline_meta_lock = threading.Lock()


def _company_pipeline_state(company_id: str) -> tuple[threading.Lock, dict]:
    """Transient (in-memory) run state: status / error / finished_at per report.
    Durable progress lives in tz_sync_cursor."""
    with _pipeline_meta_lock:
        if company_id not in _pipeline_states:
            _pipeline_locks[company_id] = threading.Lock()
            _pipeline_states[company_id] = {
                key: {"status": "idle", "error": None, "finished_at": None}
                for _cls, key, _label in _full_sync_plan()
            }
        return _pipeline_locks[company_id], _pipeline_states[company_id]


def _pipeline_by_key(key: str):
    """Return (PipelineClass, label) for a plan key, or (None, None)."""
    for cls, k, label in _full_sync_plan():
        if k == key:
            return cls, label
    return None, None


# ── Cursor persistence (tz_sync_cursor) ───────────────────────────────────────

def _ensure_cursor_table(conn) -> None:
    """Create tz_sync_cursor if it doesn't exist (safety net for live DBs that
    predate migration 007)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tz_sync_cursor (
                company_id     TEXT NOT NULL,
                pipeline_name  TEXT NOT NULL,
                next_page      INT  NOT NULL DEFAULT 1,
                total_items    INT,
                rows_stored    INT  NOT NULL DEFAULT 0,
                complete       BOOLEAN NOT NULL DEFAULT FALSE,
                updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (company_id, pipeline_name)
            )
            """
        )
    conn.commit()


def _read_cursor(conn, company_id: str, key: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT next_page, total_items, rows_stored, complete
                 FROM tz_sync_cursor WHERE company_id=%s AND pipeline_name=%s""",
            (company_id, key),
        )
        row = cur.fetchone()
    if not row:
        return {"next_page": 1, "total_items": None, "rows_stored": 0, "complete": False}
    return {"next_page": row[0], "total_items": row[1], "rows_stored": row[2], "complete": row[3]}


def _write_cursor(conn, company_id: str, key: str, *, next_page: int,
                  total_items, rows_stored: int, complete: bool) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tz_sync_cursor
                   (company_id, pipeline_name, next_page, total_items, rows_stored, complete, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (company_id, pipeline_name) DO UPDATE SET
                next_page   = EXCLUDED.next_page,
                total_items = EXCLUDED.total_items,
                rows_stored = EXCLUDED.rows_stored,
                complete    = EXCLUDED.complete,
                updated_at  = NOW()
            """,
            (company_id, key, next_page, total_items, rows_stored, complete),
        )
    conn.commit()


def _rebuild_canonical(company_id: str) -> None:
    """Re-derive the canonical layer the dashboard reads from. Best-effort."""
    try:
        from vinayak.canonical.tranzact_canonical import rebuild_canonical
        cdb = psycopg2.connect(DATABASE_URL)
        try:
            rebuild_canonical(cdb, company_id)
        finally:
            cdb.close()
    except Exception as exc:  # noqa: BLE001
        logger.error("Canonical rebuild for %s failed: %s", company_id, exc)


def _run_single_pipeline(company_id: str, email: str, password: str,
                         key: str, restart: bool = False,
                         refresh_only: bool = False) -> None:
    """Sync one report.

    • refresh_only → pull just the newest pages (the daily/hourly incremental);
      migration progress (next_page/complete) is left untouched unless the whole
      report fits in the refresh window.
    • otherwise → walk the remaining pages chunk-by-chunk, persisting the cursor
      after each chunk, resuming from the stored cursor unless `restart` is set."""
    import datetime as _dt
    from vinayak.adapters.tranzact.client import TranzactCreds

    lock, st = _company_pipeline_state(company_id)
    PipelineCls, _label = _pipeline_by_key(key)
    creds = TranzactCreds(email=email, password=password, base_url=TRANZACT_BASE_URL)

    def _set(**fields):
        with lock:
            st[key].update(fields)

    conn = psycopg2.connect(DATABASE_URL)
    try:
        _ensure_cursor_table(conn)
        cur = _read_cursor(conn, company_id, key)
    finally:
        conn.close()

    if restart:
        cur = {"next_page": 1, "total_items": None, "rows_stored": 0, "complete": False}

    _set(status="running", error=None)
    try:
        pipeline = PipelineCls()

        # Newest-pages refresh: when the report is already migrated, or when an
        # incremental (refresh_only) sync is requested. Pulls the top pages and
        # upserts (content-hash dedup), without disturbing migration progress.
        if refresh_only or (cur["complete"] and not restart):
            res = pipeline.run_chunk(
                company_id=company_id, creds=creds,
                start_page=1, max_pages=REFRESH_PAGES, max_seconds=CHUNK_MAX_SECONDS,
            )
            _rebuild_canonical(company_id)
            if res["reached_end"]:
                # The whole report fit in the refresh window → fully covered.
                next_page, rows_stored, complete = 1, res["rows_fetched"], True
            else:
                # Big report: keep migration progress as-is, just refresh totals.
                next_page = cur["next_page"]
                rows_stored = cur["rows_stored"]
                complete = cur["complete"]
            db = psycopg2.connect(DATABASE_URL)
            try:
                _write_cursor(db, company_id, key, next_page=next_page,
                              total_items=res["total_items"],
                              rows_stored=rows_stored, complete=complete)
            finally:
                db.close()
            _set(status="success",
                 finished_at=_dt.datetime.now(_dt.timezone.utc).isoformat())
            return

        # Migration walk: fetch chunks from next_page until the end is reached.
        next_page = max(1, cur["next_page"])
        rows_stored = cur["rows_stored"]
        while True:
            res = pipeline.run_chunk(
                company_id=company_id, creds=creds,
                start_page=next_page, max_pages=CHUNK_PAGES, max_seconds=CHUNK_MAX_SECONDS,
            )
            rows_stored += res["rows_fetched"]
            next_page = res["last_page"] + 1
            complete = res["reached_end"] or not res["more_available"]

            _rebuild_canonical(company_id)
            db = psycopg2.connect(DATABASE_URL)
            try:
                _write_cursor(
                    db, company_id, key,
                    next_page=1 if complete else next_page,
                    total_items=res["total_items"],
                    rows_stored=rows_stored, complete=complete,
                )
            finally:
                db.close()
            _set(status="running")

            if complete or res["rows_fetched"] == 0:
                break

        _set(status="success",
             finished_at=_dt.datetime.now(_dt.timezone.utc).isoformat())
        logger.info("Migration %s for %s: complete (%s rows)", key, company_id, rows_stored)
    except Exception as exc:  # noqa: BLE001
        logger.error("Migration %s for %s failed: %s", key, company_id, exc)
        _set(status="failed", error=str(exc),
             finished_at=_dt.datetime.now(_dt.timezone.utc).isoformat())


@router.get("/tranzact/sync/pipelines", summary="Per-report migration status")
def pipeline_sync_status(company_id: str = Depends(require_workspace)):
    """Per-report progress: running flag (in-memory) + durable cursor progress."""
    lock, st = _company_pipeline_state(company_id)

    cursors: dict[str, dict] = {}
    conn = _conn()
    try:
        _ensure_cursor_table(conn)
        for _cls, key, _label in _full_sync_plan():
            cursors[key] = _read_cursor(conn, company_id, key)
    except Exception as exc:
        conn.close()
        _raise_if_schema_missing(exc)
    finally:
        conn.close()

    out = []
    with lock:
        for _cls, key, label in _full_sync_plan():
            run = st[key]
            c = cursors.get(key, {})
            total = c.get("total_items")
            stored = c.get("rows_stored", 0)
            pct = (min(100, round(stored / total * 100)) if total else
                   (100 if c.get("complete") else 0))
            out.append({
                "key": key,
                "label": label,
                "status": run["status"],
                "error": run["error"],
                "finished_at": run["finished_at"],
                "rows_stored": stored,
                "total_items": total,
                "complete": bool(c.get("complete")),
                "next_page": c.get("next_page", 1),
                "percent": pct,
            })
    return {"pipelines": out}


@router.post("/tranzact/sync/pipeline/{key}", summary="Run/resume one report's migration")
def trigger_pipeline_sync(
    key: str,
    restart: bool = False,
    company_id: str = Depends(require_workspace),
):
    """Resume (or, with restart=true, re-walk from page 1) a single report's
    page migration. Returns immediately; progress is polled via GET …/pipelines."""
    PipelineCls, label = _pipeline_by_key(key)
    if PipelineCls is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown report: {key}",
        )

    lock, st = _company_pipeline_state(company_id)
    with lock:
        if st[key]["status"] == "running":
            return {"status": "already_running", "key": key}
        st[key].update(status="running", error=None)

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
        with lock:
            st[key].update(status="idle")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No TranzAct credentials found. Connect TranzAct first.",
        )

    creds = _decrypt(row[0])
    threading.Thread(
        target=_run_single_pipeline,
        args=(company_id, creds["email"], creds["password"], key, restart),
        daemon=True,
    ).start()
    logger.info("Migration %s started: %s for %s", "restart" if restart else "resume", key, company_id)
    return {"status": "started", "key": key, "label": label, "restart": restart}


# ── Sync ALL reports (onboarding) + incremental refresh (login / hourly) ───────
_all_running: dict[str, bool] = {}
_all_lock = threading.Lock()


def _load_tranzact_creds(company_id: str) -> dict | None:
    """Decrypted {email, password} for the company's active TranzAct conn, or None."""
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
    return _decrypt(row[0]) if row else None


def _run_all_pipelines(company_id: str, email: str, password: str,
                       refresh_only: bool = False, restart: bool = False) -> None:
    """Run every report sequentially in one background thread (the shared rate
    limiter serialises requests anyway).

    • restart=True  → re-walk every report from page 1, re-checking the whole
      report and re-adding any rows missing from the DB (content-hash upsert
      dedups, so nothing duplicates). This is what a manual "Sync all" does.
    • refresh_only=True → newest pages only (login/hourly incremental).
    • neither → resume each report from its stored cursor.
    """
    with _all_lock:
        if _all_running.get(company_id):
            return
        _all_running[company_id] = True
    try:
        for _cls, key, _label in _full_sync_plan():
            try:
                _run_single_pipeline(company_id, email, password, key,
                                     restart=restart, refresh_only=refresh_only)
            except Exception as exc:  # noqa: BLE001
                logger.error("sync-all %s for %s failed: %s", key, company_id, exc)
    finally:
        with _all_lock:
            _all_running[company_id] = False


@router.post("/tranzact/sync/all", summary="Sync ALL reports (background, full re-check)")
def trigger_sync_all(refresh_only: bool = False, restart: bool = True,
                     company_id: str = Depends(require_workspace)):
    """Manual "Sync all": by default re-walks EVERY report from page 1 (restart),
    re-checking the whole report and re-adding any rows missing from the DB
    (content-hash upsert dedups). Runs in the background and survives restarts.
    Poll progress via GET …/sync/pipelines.

    Pass restart=false to merely resume incomplete reports from their cursor."""
    creds = _load_tranzact_creds(company_id)
    if not creds:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No TranzAct credentials found. Connect TranzAct first.",
        )
    with _all_lock:
        if _all_running.get(company_id):
            return {"status": "already_running"}
    threading.Thread(
        target=_run_all_pipelines,
        args=(company_id, creds["email"], creds["password"], refresh_only, restart),
        daemon=True,
    ).start()
    logger.info("Sync-all started for %s (refresh_only=%s)", company_id, refresh_only)
    return {"status": "started", "refresh_only": refresh_only}


@router.post("/tranzact/sync/refresh", summary="Incremental newest-only refresh (login/hourly)")
def trigger_sync_refresh(company_id: str = Depends(require_workspace)):
    """Daily/login incremental: pull only the newest pages of every report. Safe
    to fire on every login — it's a no-op if nothing's connected or already
    running, and never disturbs an in-progress migration."""
    creds = _load_tranzact_creds(company_id)
    if not creds:
        return {"status": "no_connection"}
    with _all_lock:
        if _all_running.get(company_id):
            return {"status": "already_running"}
    threading.Thread(
        target=_run_all_pipelines,
        args=(company_id, creds["email"], creds["password"], True),
        daemon=True,
    ).start()
    logger.info("Incremental refresh started for %s", company_id)
    return {"status": "started"}


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
