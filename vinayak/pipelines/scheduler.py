"""
pipelines/scheduler.py
───────────────────────
APScheduler configuration for all 10 Vinayak Brain OS pipelines.

Every job runs an INCREMENTAL refresh (newest pages only — TranzAct has no
server-side date filter) via the cursor-aware sync, and rebuilds the canonical
layer. It never disturbs an in-progress migration. The full historical
migration is triggered separately (Settings → "Sync all").

Schedule summary — all jobs run HOURLY, staggered by minute (IST):

    :00 ar_aging          :32 process_details
    :08 sales_orders      :40 sales_invoices
    :16 purchase_orders   :44 purchase_invoices
    :24 inventory_valuation :48 grn_qir
    :52 sales_quotations  :56 process_routing

Usage:
    from vinayak.pipelines.scheduler import scheduler, start_scheduler, stop_scheduler

    start_scheduler()   # starts background thread
    ...
    stop_scheduler()    # graceful shutdown
"""
from __future__ import annotations

import logging
from typing import Callable, Iterator

import psycopg2

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from vinayak.config import DATABASE_URL, TRANZACT_BASE_URL
from vinayak.adapters.tranzact.client import TranzactCreds

# Existing pipelines
from vinayak.pipelines.ar_aging import ARAgingPipeline
from vinayak.pipelines.sales_invoices import SalesInvoicesPipeline
from vinayak.pipelines.sales_orders import SalesOrdersPipeline
from vinayak.pipelines.purchase_invoices import PurchaseInvoicesPipeline
from vinayak.pipelines.purchase_orders import PurchaseOrdersPipeline

# New pipelines
from vinayak.pipelines.grn_qir import GRNQIRPipeline
from vinayak.pipelines.sales_quotations import SalesQuotationsPipeline
from vinayak.pipelines.inventory_valuation import InventoryValuationPipeline
from vinayak.pipelines.process_routing import ProcessRoutingPipeline
from vinayak.pipelines.process_details import ProcessDetailsPipeline

logger = logging.getLogger(__name__)

_IST = "Asia/Kolkata"

# ── Pipeline singletons ───────────────────────────────────────────────────────

_ar_aging = ARAgingPipeline()
_sales_invoices = SalesInvoicesPipeline()
_sales_orders = SalesOrdersPipeline()
_purchase_invoices = PurchaseInvoicesPipeline()
_purchase_orders = PurchaseOrdersPipeline()
_grn_qir = GRNQIRPipeline()
_sales_quotations = SalesQuotationsPipeline()
_inventory_valuation = InventoryValuationPipeline()
_process_routing = ProcessRoutingPipeline()
_process_details = ProcessDetailsPipeline()


# ── Multi-tenant credential loading ───────────────────────────────────────────
# Scheduled jobs must run once PER brand, authenticating as that brand. We pull
# every active TranzAct connection from the DB, decrypt its credentials, and run
# the pipeline scoped to that company_id. A brand with no stored connection is
# simply skipped (nothing to sync).

def _iter_company_creds() -> Iterator[tuple[str, TranzactCreds]]:
    """Yield (company_id, creds) for every company with an active TranzAct connection."""
    from vinayak.api.routes.connections import _decrypt

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT company_id, encrypted_credentials
                   FROM tool_connections
                   WHERE tool_name = 'tranzact' AND is_active = TRUE""",
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    for company_id, blob in rows:
        try:
            cred = _decrypt(blob)
            yield company_id, TranzactCreds(
                email=cred["email"], password=cred["password"], base_url=TRANZACT_BASE_URL,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Scheduler: failed to load creds for %s: %s", company_id, exc)


def _run_for_all(name: str) -> None:
    """Incremental (newest-only) refresh of report `name` for every connected
    company — the hourly background sync.

    Delegates to the cursor-aware per-report sync in refresh_only mode, which
    pulls just the newest pages, upserts (content-hash dedup), and rebuilds the
    canonical layer. It never disturbs an in-progress migration. A failure for
    one brand is logged and never aborts the others.
    """
    from vinayak.api.routes.connections import _run_single_pipeline
    companies = list(_iter_company_creds())
    if not companies:
        logger.info("Scheduler: %s — no connected workspaces, skipping", name)
        return
    for company_id, creds in companies:
        logger.info("Scheduler: hourly refresh %s for %s", name, company_id)
        try:
            _run_single_pipeline(company_id, creds.email, creds.password,
                                  name, refresh_only=True)
        except Exception as exc:  # noqa: BLE001
            logger.error("Scheduler: %s refresh failed for %s: %s", name, company_id, exc)


# ── Job functions ─────────────────────────────────────────────────────────────

def _run_ar_aging() -> None:
    _run_for_all("ar_aging")


def _run_sales_orders() -> None:
    _run_for_all("sales_orders")


def _run_purchase_orders() -> None:
    _run_for_all("purchase_orders")


def _run_inventory_valuation() -> None:
    _run_for_all("inventory_valuation")


def _run_process_details() -> None:
    _run_for_all("process_details")


def _run_sales_invoices() -> None:
    _run_for_all("sales_invoices")


def _run_purchase_invoices() -> None:
    _run_for_all("purchase_invoices")


def _run_grn_qir() -> None:
    _run_for_all("grn_qir")


def _run_sales_quotations() -> None:
    _run_for_all("sales_quotations")


def _run_process_routing() -> None:
    _run_for_all("process_routing")


# ── Scheduler instance ────────────────────────────────────────────────────────

scheduler = AsyncIOScheduler(timezone=_IST)

# -- Hourly jobs (staggered by minute to avoid rate-limit bursting) -----------

scheduler.add_job(
    _run_ar_aging,
    trigger=CronTrigger(minute=0, timezone=_IST),
    id="ar_aging_hourly",
    name="AR Aging (hourly, :00)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_sales_orders,
    trigger=CronTrigger(minute=8, timezone=_IST),
    id="sales_orders_hourly",
    name="Sales Orders (hourly, :08)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_purchase_orders,
    trigger=CronTrigger(minute=16, timezone=_IST),
    id="purchase_orders_hourly",
    name="Purchase Orders (hourly, :16)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_inventory_valuation,
    trigger=CronTrigger(minute=24, timezone=_IST),
    id="inventory_valuation_hourly",
    name="Inventory Valuation (hourly, :24)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_process_details,
    trigger=CronTrigger(minute=32, timezone=_IST),
    id="process_details_hourly",
    name="Process Details (hourly, :32)",
    replace_existing=True,
    misfire_grace_time=300,
)

# -- Formerly-daily reports — now also hourly (newest-only refresh) ----------

scheduler.add_job(
    _run_sales_invoices,
    trigger=CronTrigger(minute=40, timezone=_IST),
    id="sales_invoices_hourly",
    name="Sales Invoices (hourly, :40)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_purchase_invoices,
    trigger=CronTrigger(minute=44, timezone=_IST),
    id="purchase_invoices_hourly",
    name="Purchase Invoices (hourly, :44)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_grn_qir,
    trigger=CronTrigger(minute=48, timezone=_IST),
    id="grn_qir_hourly",
    name="GRN / QIR (hourly, :48)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_sales_quotations,
    trigger=CronTrigger(minute=52, timezone=_IST),
    id="sales_quotations_hourly",
    name="Sales Quotations (hourly, :52)",
    replace_existing=True,
    misfire_grace_time=300,
)

scheduler.add_job(
    _run_process_routing,
    trigger=CronTrigger(minute=56, timezone=_IST),
    id="process_routing_hourly",
    name="Process Routing (hourly, :56)",
    replace_existing=True,
    misfire_grace_time=300,
)


# ── Public start / stop helpers ───────────────────────────────────────────────

def start_scheduler() -> None:
    """Start the APScheduler background loop (idempotent)."""
    if not scheduler.running:
        scheduler.start()
        logger.info(
            "Scheduler started — %d jobs registered (timezone: %s)",
            len(scheduler.get_jobs()),
            _IST,
        )
    else:
        logger.warning("start_scheduler() called but scheduler is already running.")


def stop_scheduler() -> None:
    """Gracefully shut down the APScheduler background loop."""
    if scheduler.running:
        scheduler.shutdown(wait=True)
        logger.info("Scheduler stopped.")
    else:
        logger.warning("stop_scheduler() called but scheduler is not running.")
