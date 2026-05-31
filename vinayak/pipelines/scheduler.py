"""
pipelines/scheduler.py
───────────────────────
APScheduler configuration for all 10 Vinayak Brain OS pipelines.

Schedule summary (all times in IST, Asia/Kolkata):

  Hourly jobs  — run every hour at the specified minute offset:
    :00  ar_aging          — today only (point-in-time AR snapshot)
    :08  sales_orders      — last 7 days
    :16  purchase_orders   — last 7 days
    :24  inventory_valuation — snapshot (no date window)
    :32  process_details   — last 7 days

  Daily jobs   — run once at 3 AM IST, staggered by 5 minutes:
    03:00  sales_invoices      — last 30 days
    03:05  purchase_invoices   — last 30 days
    03:10  grn_qir             — last 30 days
    03:15  sales_quotations    — last 30 days
    03:20  process_routing     — last 30 days

Usage:
    from vinayak.pipelines.scheduler import scheduler, start_scheduler, stop_scheduler

    start_scheduler()   # starts background thread
    ...
    stop_scheduler()    # graceful shutdown
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
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


def _run_for_all(pipeline, name: str, days_back: int) -> None:
    """Run `pipeline` for every company with stored TranzAct creds.

    days_back=0 → today-only snapshot (e.g. AR aging, inventory valuation).
    A failure for one brand is logged and never aborts the others.
    """
    today = date.today()
    from_date = today - timedelta(days=days_back)
    companies = list(_iter_company_creds())
    if not companies:
        logger.info("Scheduler: %s — no connected workspaces, skipping", name)
        return
    for company_id, creds in companies:
        logger.info("Scheduler: %s for %s (%s → %s)", name, company_id, from_date, today)
        try:
            pipeline.run(from_date, today, company_id=company_id, creds=creds)
        except Exception as exc:  # noqa: BLE001
            logger.error("Scheduler: %s failed for %s: %s", name, company_id, exc)


# ── Job functions ─────────────────────────────────────────────────────────────

def _run_ar_aging() -> None:
    _run_for_all(_ar_aging, "ar_aging", days_back=0)


def _run_sales_orders() -> None:
    _run_for_all(_sales_orders, "sales_orders", days_back=7)


def _run_purchase_orders() -> None:
    _run_for_all(_purchase_orders, "purchase_orders", days_back=7)


def _run_inventory_valuation() -> None:
    _run_for_all(_inventory_valuation, "inventory_valuation", days_back=0)


def _run_process_details() -> None:
    _run_for_all(_process_details, "process_details", days_back=7)


def _run_sales_invoices() -> None:
    _run_for_all(_sales_invoices, "sales_invoices", days_back=30)


def _run_purchase_invoices() -> None:
    _run_for_all(_purchase_invoices, "purchase_invoices", days_back=30)


def _run_grn_qir() -> None:
    _run_for_all(_grn_qir, "grn_qir", days_back=30)


def _run_sales_quotations() -> None:
    _run_for_all(_sales_quotations, "sales_quotations", days_back=30)


def _run_process_routing() -> None:
    _run_for_all(_process_routing, "process_routing", days_back=30)


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

# -- Daily jobs at 3 AM IST (staggered by 5 minutes each) --------------------

scheduler.add_job(
    _run_sales_invoices,
    trigger=CronTrigger(hour=3, minute=0, timezone=_IST),
    id="sales_invoices_daily",
    name="Sales Invoices (daily, 03:00 IST)",
    replace_existing=True,
    misfire_grace_time=600,
)

scheduler.add_job(
    _run_purchase_invoices,
    trigger=CronTrigger(hour=3, minute=5, timezone=_IST),
    id="purchase_invoices_daily",
    name="Purchase Invoices (daily, 03:05 IST)",
    replace_existing=True,
    misfire_grace_time=600,
)

scheduler.add_job(
    _run_grn_qir,
    trigger=CronTrigger(hour=3, minute=10, timezone=_IST),
    id="grn_qir_daily",
    name="GRN / QIR (daily, 03:10 IST)",
    replace_existing=True,
    misfire_grace_time=600,
)

scheduler.add_job(
    _run_sales_quotations,
    trigger=CronTrigger(hour=3, minute=15, timezone=_IST),
    id="sales_quotations_daily",
    name="Sales Quotations (daily, 03:15 IST)",
    replace_existing=True,
    misfire_grace_time=600,
)

scheduler.add_job(
    _run_process_routing,
    trigger=CronTrigger(hour=3, minute=20, timezone=_IST),
    id="process_routing_daily",
    name="Process Routing (daily, 03:20 IST)",
    replace_existing=True,
    misfire_grace_time=600,
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
