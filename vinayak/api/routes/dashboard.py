"""
api/routes/dashboard.py
────────────────────────
All 17 dashboard panel endpoints + sync health.

Every endpoint returns the same JSON envelope:
    {
        "data":  { ... },          ← result of the query function
        "meta": {
            "report_id":     int,
            "last_synced_at": str | null,
            "stale":          bool
        }
    }

The data dict is what gets rendered in the dashboard panels.
The meta dict is shown to the user as the "last synced X min ago" stamp.
"""
from __future__ import annotations

import psycopg2
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import logging
logger = logging.getLogger(__name__)

from vinayak.config import DATABASE_URL
from vinayak.schema import queries
from vinayak.memory import store as memory
from vinayak.api.routes.workspaces import require_workspace

router = APIRouter()


def _conn():
    """Open a new psycopg2 connection. Caller is responsible for closing."""
    try:
        return psycopg2.connect(DATABASE_URL)
    except psycopg2.OperationalError as exc:
        logger.error("DB connection failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — check DATABASE_URL (Supabase direct connection, port 5432)",
        ) from exc


def _envelope(data: dict, report_id: int) -> dict:
    """Wrap a query result in the standard API envelope."""
    return {
        "data": {k: v for k, v in data.items()
                 if k not in ("last_synced_at", "stale")},
        "meta": {
            "report_id":     report_id,
            "last_synced_at": data.get("last_synced_at"),
            "stale":          data.get("stale", False),
        },
    }


# ════════════════════════════════════════════════════════════════════════════
# STRATEGIC PANELS (daily cache)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/revenue/summary")
def revenue_summary(
    period_days: int = Query(default=30, ge=7, le=365),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    company_id: str = Depends(require_workspace),
):
    """S1 — Revenue KPIs for the selected period (latest-anchored, or explicit range)."""
    conn = _conn()
    try:
        data = queries.get_revenue_summary(conn, company_id, period_days, start, end)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/revenue/trend")
def revenue_trend(months: int = Query(default=6, ge=1, le=24), company_id: str = Depends(require_workspace)):
    """S2 — Monthly revenue trend (bar chart data)."""
    conn = _conn()
    try:
        data = queries.get_revenue_trend(conn, company_id, months)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/revenue/daily")
def revenue_daily(
    period_days: int = Query(default=90, ge=7, le=400),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    company_id: str = Depends(require_workspace),
):
    """S2b — Daily revenue series (line chart data)."""
    conn = _conn()
    try:
        data = queries.get_revenue_daily(conn, company_id, period_days, start, end)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/revenue/concentration")
def customer_concentration(
    period_days: int = Query(default=30, ge=7, le=365),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    company_id: str = Depends(require_workspace),
):
    """S3 — Customer revenue concentration (doughnut chart)."""
    conn = _conn()
    try:
        data = queries.get_customer_concentration(conn, company_id, period_days, start, end)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/revenue/customers")
def top_customers_revenue(
    period_days: int = Query(default=30, ge=7, le=365),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    company_id: str = Depends(require_workspace),
):
    """S4 — Top customers by revenue."""
    conn = _conn()
    try:
        data = queries.get_top_customers_revenue(conn, company_id, period_days, start, end)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/revenue/skus")
def top_skus_revenue(
    period_days: int = Query(default=30, ge=7, le=365),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    company_id: str = Depends(require_workspace),
):
    """S5 — Top SKUs by revenue."""
    conn = _conn()
    try:
        data = queries.get_top_skus_revenue(conn, company_id, period_days, start, end)
    finally:
        conn.close()
    return _envelope(data, report_id=29)


# ════════════════════════════════════════════════════════════════════════════
# ROW-LEVEL DETAIL LISTS (server-side search / date-filter / pagination)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/sales/invoices")
def sales_invoices_list(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="invoice_date"),
    direction: str = Query(default="desc"),
    company_id: str = Depends(require_workspace),
):
    """Paginated, searchable, date-filterable sales invoice line items."""
    conn = _conn()
    try:
        data = queries.get_sales_invoices_list(
            conn, company_id,
            start=start, end=end, search=search,
            page=page, page_size=page_size, sort=sort, direction=direction,
        )
    finally:
        conn.close()
    return _envelope(data, report_id=29)


@router.get("/ar/invoices")
def ar_invoices_list(
    search: str | None = Query(default=None),
    bucket: str | None = Query(default=None),
    overdue_only: bool = Query(default=False),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="outstanding_amount"),
    direction: str = Query(default="desc"),
    company_id: str = Depends(require_workspace),
):
    """Paginated, searchable AR invoice line items with bucket / overdue filters."""
    conn = _conn()
    try:
        data = queries.get_ar_invoices_list(
            conn, company_id,
            search=search, bucket=bucket, overdue_only=overdue_only,
            page=page, page_size=page_size, sort=sort, direction=direction,
        )
    finally:
        conn.close()
    return _envelope(data, report_id=102)


@router.get("/purchases/invoices")
def purchase_invoices_list(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    search: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="invoice_date"),
    direction: str = Query(default="desc"),
    company_id: str = Depends(require_workspace),
):
    """Paginated, searchable, date-filterable purchase invoice line items."""
    conn = _conn()
    try:
        data = queries.get_purchase_invoices_list(
            conn, company_id,
            start=start, end=end, search=search,
            page=page, page_size=page_size, sort=sort, direction=direction,
        )
    finally:
        conn.close()
    return _envelope(data, report_id=77)


@router.get("/orders/list")
def sales_orders_list(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="order_date"),
    direction: str = Query(default="desc"),
    company_id: str = Depends(require_workspace),
):
    """Paginated, searchable sales-order line items with status filter."""
    conn = _conn()
    try:
        data = queries.get_sales_orders_list(
            conn, company_id,
            start=start, end=end, search=search, status=status,
            page=page, page_size=page_size, sort=sort, direction=direction,
        )
    finally:
        conn.close()
    return _envelope(data, report_id=2)


@router.get("/purchases/po-list")
def purchase_orders_list(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="po_date"),
    direction: str = Query(default="desc"),
    company_id: str = Depends(require_workspace),
):
    """Paginated, searchable purchase-order line items with status filter."""
    conn = _conn()
    try:
        data = queries.get_purchase_orders_list(
            conn, company_id,
            start=start, end=end, search=search, status=status,
            page=page, page_size=page_size, sort=sort, direction=direction,
        )
    finally:
        conn.close()
    return _envelope(data, report_id=3)


@router.get("/production/list")
def production_list(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="production_date"),
    direction: str = Query(default="desc"),
    company_id: str = Depends(require_workspace),
):
    """Paginated, searchable production process records with status filter."""
    conn = _conn()
    try:
        data = queries.get_production_list(
            conn, company_id,
            start=start, end=end, search=search, status=status,
            page=page, page_size=page_size, sort=sort, direction=direction,
        )
    finally:
        conn.close()
    return _envelope(data, report_id=25)


@router.get("/inventory/list")
def inventory_list(
    search: str | None = Query(default=None),
    category: str | None = Query(default=None),
    page: int = Query(default=0, ge=0),
    page_size: int = Query(default=25, ge=1, le=100),
    sort: str = Query(default="total_value"),
    direction: str = Query(default="desc"),
    company_id: str = Depends(require_workspace),
):
    """Paginated, searchable inventory valuation rows with category filter."""
    conn = _conn()
    try:
        data = queries.get_inventory_list(
            conn, company_id,
            search=search, category=category,
            page=page, page_size=page_size, sort=sort, direction=direction,
        )
    finally:
        conn.close()
    return _envelope(data, report_id=9)


@router.get("/inventory/summary")
def inventory_summary(company_id: str = Depends(require_workspace)):
    """S6 — Inventory KPIs (current stock snapshot)."""
    conn = _conn()
    try:
        data = queries.get_inventory_summary(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=9)


@router.get("/inventory/categories")
def inventory_by_category(company_id: str = Depends(require_workspace)):
    """S7 — Stock value by product category."""
    conn = _conn()
    try:
        data = queries.get_inventory_by_category(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=9)


@router.get("/inventory/top-holdings")
def top_stock_holdings(company_id: str = Depends(require_workspace)):
    """S8 — Highest-value SKUs in stock."""
    conn = _conn()
    try:
        data = queries.get_top_stock_holdings(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=9)


@router.get("/purchases/summary")
def purchases_summary(period_days: int = Query(default=30, ge=7, le=365), company_id: str = Depends(require_workspace)):
    """S9 — Purchase spend KPIs."""
    conn = _conn()
    try:
        data = queries.get_purchases_summary(conn, company_id, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=77)


@router.get("/purchases/vendors")
def top_vendors_spend(period_days: int = Query(default=30, ge=7, le=365), company_id: str = Depends(require_workspace)):
    """S10 — Top vendors by purchase spend."""
    conn = _conn()
    try:
        data = queries.get_top_vendors_spend(conn, company_id, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=77)


@router.get("/production/summary")
def production_summary(period_days: int = Query(default=30, ge=7, le=365), company_id: str = Depends(require_workspace)):
    """S11 — Production KPIs (FG output, reject rate)."""
    conn = _conn()
    try:
        data = queries.get_production_summary(conn, company_id, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=25)


@router.get("/orders/summary")
def order_book_summary(company_id: str = Depends(require_workspace)):
    """S12 — Sales order book KPIs."""
    conn = _conn()
    try:
        data = queries.get_order_book_summary(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=2)


@router.get("/quotes/summary")
def quote_summary(period_days: int = Query(default=30, ge=7, le=365), company_id: str = Depends(require_workspace)):
    """S13 — Sales quotation pipeline KPIs."""
    conn = _conn()
    try:
        data = queries.get_quote_summary(conn, company_id, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=8)


@router.get("/grn/summary")
def grn_summary(period_days: int = Query(default=30, ge=7, le=365), company_id: str = Depends(require_workspace)):
    """S14 — Goods Received Note KPIs."""
    conn = _conn()
    try:
        data = queries.get_grn_summary(conn, company_id, period_days)
    finally:
        conn.close()
    return _envelope(data, report_id=34)


@router.get("/bom/coverage")
def bom_coverage(company_id: str = Depends(require_workspace)):
    """S15 — BOM / routing coverage."""
    conn = _conn()
    try:
        data = queries.get_bom_coverage(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=86)


# ════════════════════════════════════════════════════════════════════════════
# OPERATIONAL PANELS (hourly cache — Sandeep's morning alerts)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/ar/aging")
def ar_aging(company_id: str = Depends(require_workspace)):
    """O1 — AR aging buckets + overdue summary."""
    conn = _conn()
    try:
        data = queries.get_ar_summary(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=102)


@router.get("/ar/customers")
def ar_customer_exposure(company_id: str = Depends(require_workspace)):
    """O2 — AR exposure per customer."""
    conn = _conn()
    try:
        data = queries.get_ar_customer_exposure(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=102)


@router.get("/purchases/overdue-pos")
def overdue_pos(company_id: str = Depends(require_workspace)):
    """O3 — Overdue purchase orders."""
    conn = _conn()
    try:
        data = queries.get_overdue_pos(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=3)


@router.get("/purchases/open-pos")
def open_pos(company_id: str = Depends(require_workspace)):
    """O3b — Open PO book (open vs overdue distinct) + by-vendor breakdown."""
    conn = _conn()
    try:
        data = queries.get_open_pos(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=3)


@router.get("/production/wip")
def production_wip(company_id: str = Depends(require_workspace)):
    """O4 — WIP and production status breakdown."""
    conn = _conn()
    try:
        data = queries.get_production_wip(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=25)


@router.get("/orders/overdue")
def overdue_orders(company_id: str = Depends(require_workspace)):
    """O5 — Overdue order confirmations."""
    conn = _conn()
    try:
        data = queries.get_overdue_orders(conn, company_id)
    finally:
        conn.close()
    return _envelope(data, report_id=2)


# ════════════════════════════════════════════════════════════════════════════
# SYNC HEALTH (always live — reads from tz_sync_runs directly)
# ════════════════════════════════════════════════════════════════════════════

@router.get("/sync/health")
def sync_health(company_id: str = Depends(require_workspace)):
    """Freshness status for all 10 pipelines. Never cached."""
    conn = _conn()
    try:
        data = queries.get_sync_health(conn, company_id)
    finally:
        conn.close()
    return data


@router.get("/ingest/quality")
def ingest_quality(company_id: str = Depends(require_workspace)):
    """Layer-0 data-quality: canonical mapping coverage + top unmapped issues."""
    conn = _conn()
    try:
        data = queries.get_ingest_quality(conn, company_id)
    finally:
        conn.close()
    return data


# ════════════════════════════════════════════════════════════════════════════
# LAYER 2 — Business profile + memory facts
# ════════════════════════════════════════════════════════════════════════════

class ProfileIn(BaseModel):
    industry: str | None = None
    sub_vertical: str | None = None
    fiscal_year_start: str | None = None
    gst_registered: bool | None = None
    base_currency: str | None = None
    healthy_margin_pct: float | None = None
    seasonality: str | None = None
    key_customers: list | None = None
    kpis: str | None = None
    extras: dict | None = None


class FactIn(BaseModel):
    entity_type: str
    entity_ref: str
    claim_key: str
    claim_value: object
    origin: str = "user_confirmed"
    confidence: float = 1.0
    valid_until: str | None = None
    source_msg_id: str | None = None


@router.get("/profile")
def get_profile(company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"profile": memory.get_profile(conn, company_id)}
    finally:
        conn.close()


@router.put("/profile")
def put_profile(body: ProfileIn, company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"profile": memory.upsert_profile(conn, company_id, body.model_dump(exclude_none=True))}
    finally:
        conn.close()


@router.get("/memory")
def list_memory(
    company_id: str = Depends(require_workspace),
    entity_ref: str | None = Query(None),
):
    conn = _conn()
    try:
        return {"facts": memory.active_facts(conn, company_id, entity_ref)}
    finally:
        conn.close()


@router.post("/memory")
def add_memory(body: FactIn, company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        fact = memory.write_fact(
            conn, company_id,
            entity_type=body.entity_type, entity_ref=body.entity_ref,
            claim_key=body.claim_key, claim_value=body.claim_value,
            origin=body.origin, confidence=body.confidence,
            valid_until=body.valid_until, source_msg_id=body.source_msg_id,
        )
        return {"fact": fact}
    finally:
        conn.close()


@router.delete("/memory/{fact_id}")
def delete_memory(fact_id: str, company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        memory.supersede_fact(conn, company_id, fact_id)
        return {"ok": True}
    finally:
        conn.close()


@router.post("/memory/revalidate")
def revalidate_memory(company_id: str = Depends(require_workspace)):
    """Run the decay sweep: flag time-expired + data-contradicted facts as stale."""
    conn = _conn()
    try:
        return memory.run_decay(conn, company_id)
    finally:
        conn.close()


@router.post("/sync/trigger/{pipeline_name}")
def trigger_sync(
    pipeline_name: str,
    company_id: str = Depends(require_workspace),
):
    """
    Manually trigger a pipeline run (cache invalidation) for this workspace,
    using the workspace's own stored TranzAct credentials.
    Runs synchronously — response returns after the sync completes.
    Only available for the 5 hourly pipelines (to avoid triggering heavy daily syncs).
    """
    from datetime import date, timedelta
    from vinayak.pipelines import (
        ar_aging as ar_mod,
        sales_orders as so_mod,
        purchase_orders as po_mod,
        inventory_valuation as inv_mod,
        process_details as pd_mod,
    )

    ALLOWED = {
        "ar_aging":             (ar_mod.ARAgingPipeline,          1, 1),
        "sales_orders":         (so_mod.SalesOrdersPipeline,      7, 7),
        "purchase_orders":      (po_mod.PurchaseOrdersPipeline,   7, 7),
        "inventory_valuation":  (inv_mod.InventoryValuationPipeline, 1, 1),
        "process_details":      (pd_mod.ProcessDetailsPipeline,   7, 7),
    }

    if pipeline_name not in ALLOWED:
        raise HTTPException(
            400,
            detail=f"Manual trigger only available for: {list(ALLOWED.keys())}"
        )

    PipelineClass, from_days, to_days = ALLOWED[pipeline_name]
    today = date.today()
    from_date = today - timedelta(days=from_days)
    to_date = today

    # Load this workspace's TranzAct credentials so the run authenticates as —
    # and tags data for — the right brand.
    from vinayak.config import TRANZACT_BASE_URL
    from vinayak.adapters.tranzact.client import TranzactCreds
    from vinayak.api.routes.connections import _decrypt

    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT encrypted_credentials FROM tool_connections
                   WHERE company_id = %s AND tool_name = 'tranzact' AND is_active = TRUE""",
                (company_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(404, detail="No TranzAct credentials for this workspace.")

    cred = _decrypt(row[0])
    creds = TranzactCreds(email=cred["email"], password=cred["password"], base_url=TRANZACT_BASE_URL)

    try:
        PipelineClass().run(from_date, to_date, company_id=company_id, creds=creds)
    except Exception as exc:
        raise HTTPException(500, detail=f"Pipeline failed: {exc}")

    return {"status": "ok", "pipeline": pipeline_name,
            "from_date": str(from_date), "to_date": str(to_date)}
