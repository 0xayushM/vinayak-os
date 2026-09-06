"""
tools/read_tools.py
────────────────────
Layer 7 — the READ tools. Each wraps a proven, deterministic query function from
schema/queries.py and exposes it through the tool contract so the agent (Layer 8)
and any MCP client can call the business as a tool.

Nothing here computes anything new: a read tool is a thin, safe shell over a query
function that already returns pre-aggregated, capped, source-stamped data. Every
scalar KPI the tool returns is also tagged as Evidence, so the same numeric-guard
that protects the Ask engine protects the agent — the model may only state a
number a tool actually returned.

All tools here are side_effect="read" → they execute inline (never propose). Money
and action tools register separately, later, and only ever propose.

Registration is idempotent: call register_all() at startup (and in tests). It
skips any tool already present, so it is safe to call more than once.
"""
from __future__ import annotations

from typing import Any, Callable

from vinayak.domain.models import Evidence
from vinayak.domain.money import Money
from vinayak.query import service as queries   # the read door (proxies the repository)
from vinayak.tools import registry
from vinayak.tools.contract import Tool, ToolInput, ToolResult


# ── evidence formatting ───────────────────────────────────────────────────────
def _display(value: Any, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "money":
        return Money.spaced(value)
    if kind == "pct":   return f"{value}%"
    if kind == "days":  return f"{value} days"
    return str(value)


def _evidence(prefix: str, data: dict, fields: list[tuple[str, str, str]]) -> list[Evidence]:
    """Build Evidence for each present scalar field. fields: (key, label, kind)."""
    out: list[Evidence] = []
    for key, label, kind in fields:
        if key in data and data[key] is not None:
            out.append(Evidence(id=f"{prefix}:{key}", label=label,
                                value=data[key], display=_display(data[key], kind)))
    return out


def _fresh(data: dict, key: str) -> bool:
    """Freshness signal for the confidence gate. Most query functions carry a
    `stale` flag; the meta tools report health under their own key instead."""
    if key == "stale":
        return not bool(data.get("stale", False))
    return bool(data.get(key, True))


def _make(name: str, description: str, query_fn: Callable,
          params: tuple[str, ...] = (), inputs: dict[str, ToolInput] | None = None,
          ev_fields: list[tuple[str, str, str]] | None = None,
          source: str = "canonical", fresh_key: str = "stale") -> Tool:
    """Build (but do not yet register) a read tool wrapping a query function.
    `params` are the query-fn kwargs the model may pass; None values are dropped."""
    ev_fields = ev_fields or []

    def fn(ctx, **kwargs) -> ToolResult:
        args = {k: kwargs[k] for k in params if kwargs.get(k) is not None}
        try:
            data = query_fn(ctx.conn, ctx.company_id, **args)
        except Exception as exc:  # noqa: BLE001 — a tool bug must not kill the loop
            return ToolResult.fail(f"{name} failed: {exc}")
        return ToolResult(
            data=data,
            evidence=_evidence(name, data, ev_fields),
            quality={"data_fresh": _fresh(data, fresh_key), "source": source},
        )

    return Tool(name=name, description=description, inputs=inputs or {},
                side_effect="read", fn=fn)


_DAYS = {"days": ToolInput(int, "Trailing window in days", required=False)}
_MONTHS = {"months": ToolInput(int, "Number of months (2–24)", required=False)}
_PERIOD = {"period_days": ToolInput(int, "Trailing window in days", required=False)}
_WINDOW = {"window_days": ToolInput(int, "Trailing window in days", required=False)}

# ── the read-tool catalog ─────────────────────────────────────────────────────
_TOOLS: list[Tool] = [
    # Finance
    _make("finance.get_overview",
          "One-screen finance snapshot: revenue, outstanding, overdue, DSO, and the collections shortlist.",
          queries.get_finance_overview,
          ev_fields=[("revenue_goods", "Revenue (goods)", "money"),
                     ("outstanding", "Outstanding", "money"),
                     ("overdue", "Overdue", "money"),
                     ("overdue_pct", "Overdue %", "pct"),
                     ("dso_days", "DSO", "days")]),
    _make("finance.get_collections_priority",
          "Who to chase first: overdue receivables ranked by recovery impact (amount × days overdue).",
          queries.get_collections_priority,
          ev_fields=[("total_overdue", "Total overdue", "money"),
                     ("top_share_pct", "Top customer share", "pct")]),
    _make("finance.get_credit_risk",
          "Per-customer deterministic credit flags (over-exposed / stretching terms / concentrated) with a hold/watch verdict.",
          queries.get_credit_risk_flags,
          ev_fields=[("hold_count", "Hold", "count"), ("watch_count", "Watch", "count")]),
    _make("finance.get_dso",
          "Days Sales Outstanding — how long cash sits in customers' pockets.",
          queries.get_dso, params=("days",), inputs=_DAYS,
          ev_fields=[("dso_days", "DSO", "days"), ("outstanding", "Outstanding", "money")]),
    _make("finance.get_monthly_sales",
          "Monthly sales (goods value) for the trailing months, each with its month-over-month % change.",
          queries.get_sales_monthly_comparison, params=("months",), inputs=_MONTHS,
          ev_fields=[("best_revenue", "Best month", "money")]),
    _make("finance.get_cash_movement",
          "Monthly money in (sales) vs out (purchase spend) and the net.",
          queries.get_monthly_cashflow, params=("months",), inputs=_MONTHS,
          ev_fields=[("total_in", "Money in", "money"), ("total_out", "Money out", "money"),
                     ("net", "Net", "money")]),
    _make("finance.get_customers",
          "Per-customer finance snapshot for every customer: revenue, outstanding, overdue, credit verdict.",
          queries.get_customer_finance_list,
          ev_fields=[("customer_count", "Customers", "count")]),
    # Revenue
    _make("revenue.get_summary",
          "Revenue KPIs: goods value, invoice total, YTD, monthly average, invoice & customer counts.",
          queries.get_revenue_summary,
          ev_fields=[("period_total_goods", "Revenue (goods)", "money"),
                     ("period_total_invoiced", "Revenue (invoiced)", "money"),
                     ("ytd_total", "YTD", "money")]),
    _make("revenue.get_concentration",
          "Customer revenue concentration — how dependent the business is on its top customers.",
          queries.get_customer_concentration),
    _make("revenue.get_top_customers",
          "Top customers by revenue, with each one's share of the total.",
          queries.get_top_customers_revenue),
    _make("revenue.get_by_category",
          "Revenue split by product category.",
          queries.get_sales_by_category),
    # Receivables
    _make("ar.get_summary",
          "Accounts receivable: total outstanding, overdue, aging buckets, top exposures.",
          queries.get_ar_summary,
          ev_fields=[("total_outstanding", "Total outstanding", "money"),
                     ("overdue_value", "Overdue", "money")]),
    _make("ar.get_exposure",
          "Receivables exposure per customer (who holds the most of our money).",
          queries.get_ar_customer_exposure),
    # Inventory
    _make("inventory.get_summary",
          "Inventory valuation: total stock value, SKU count, negative-stock flags.",
          queries.get_inventory_summary,
          ev_fields=[("total_value", "Stock value", "money")]),
    _make("inventory.get_dead_stock",
          "Dead stock: SKUs with no sales in the last 90 days — capital frozen on shelves.",
          queries.get_dead_stock),
    # Purchases
    _make("purchases.get_summary",
          "Purchase spend KPIs and vendor/invoice counts.",
          queries.get_purchases_summary,
          ev_fields=[("period_spend_goods", "Spend (goods)", "money"),
                     ("period_spend_invoiced", "Spend (invoiced)", "money")]),
    _make("purchases.get_top_vendors",
          "Top vendors by purchase spend, with each one's share of the total.",
          queries.get_top_vendors_spend),
    _make("purchases.get_open_pos",
          "Open purchase orders: how much is committed to vendors and not yet received, split by vendor.",
          queries.get_open_pos,
          ev_fields=[("open_count", "Open POs", "count"), ("open_value", "Open PO value", "money"),
                     ("overdue_count", "Overdue POs", "count"),
                     ("overdue_value", "Overdue PO value", "money")]),
    _make("purchases.get_overdue_pos",
          "Purchase orders past their expected date — inbound material that is late, ranked by value at risk.",
          queries.get_overdue_pos,
          ev_fields=[("total_overdue_count", "Overdue POs", "count"),
                     ("total_value_at_risk", "Value at risk", "money")]),
    # Revenue (trend & SKU detail)
    _make("revenue.get_trend",
          "Monthly revenue series for the trailing months — the shape of the top line over time.",
          queries.get_revenue_trend, params=("months",), inputs=_MONTHS),
    _make("revenue.get_daily",
          "Daily revenue series for the trailing window — for spotting spikes, gaps and pace within a month.",
          queries.get_revenue_daily, params=("period_days",), inputs=_PERIOD),
    _make("revenue.get_top_skus",
          "Best-selling SKUs by revenue in the window, with quantity and invoice count.",
          queries.get_top_skus_revenue, params=("period_days",), inputs=_PERIOD),
    _make("revenue.get_slow_skus",
          "Worst-selling SKUs by revenue — the tail of the catalogue that barely moves.",
          queries.get_bottom_skus_revenue, params=("period_days",), inputs=_PERIOD),
    # Customers (movement)
    _make("customers.get_changes",
          "Customers whose buying changed materially in the window — grew, shrank, or went quiet.",
          queries.get_customer_changes, params=("window_days",), inputs=_WINDOW),
    _make("customers.get_movement",
          "New, returning and lapsed customers over the recent window.",
          queries.get_customer_movement,
          params=("recent_days",),
          inputs={"recent_days": ToolInput(int, "Recent window in days", required=False)}),
    # Inventory (detail)
    _make("inventory.get_by_category",
          "Stock value and SKU count split by product category.",
          queries.get_inventory_by_category),
    _make("inventory.get_top_holdings",
          "The SKUs holding the most capital — largest stock value on hand.",
          queries.get_top_stock_holdings),
    _make("inventory.get_reorder_alert",
          "SKUs about to run out: days of cover left at the recent sales velocity.",
          queries.get_reorder_alert, params=("cover_days",),
          inputs={"cover_days": ToolInput(int, "Flag SKUs with fewer than this many days of cover", required=False)}),
    _make("inventory.get_turnover",
          "Inventory turnover: turns per year and days inventory outstanding (DIO).",
          queries.get_inventory_turnover, params=("window_days",), inputs=_WINDOW,
          ev_fields=[("turns", "Turns/yr", "count"), ("dio_days", "DIO", "days"),
                     ("inventory_value", "Inventory value", "money"),
                     ("annual_sales", "Annualised sales", "money")]),
    # Order book
    _make("orders.get_book_summary",
          "The order book: open sales orders, their value, dispatch progress and how many are overdue.",
          queries.get_order_book_summary,
          ev_fields=[("open_order_count", "Open orders", "count"),
                     ("open_order_value", "Order book value", "money"),
                     ("dispatched_pct", "Dispatched", "pct"),
                     ("overdue_count", "Overdue orders", "count")]),
    _make("orders.get_overdue",
          "Sales orders past their delivery date, ranked by value — what customers are waiting on.",
          queries.get_overdue_orders,
          ev_fields=[("total_overdue_count", "Overdue orders", "count"),
                     ("total_value", "Overdue value", "money")]),
    # Production
    _make("production.get_summary",
          "Production output for the window: finished goods produced, rejects, reject rate, WIP and completed counts.",
          queries.get_production_summary, params=("period_days",), inputs=_PERIOD,
          ev_fields=[("fg_produced", "FG produced", "count"), ("rejected", "Rejected", "count"),
                     ("reject_rate_pct", "Reject rate", "pct"), ("wip_count", "WIP", "count")]),
    _make("production.get_wip",
          "Work in progress: open work orders by status, with planned vs produced quantity.",
          queries.get_production_wip),
    _make("production.get_bom_coverage",
          "How much of the catalogue has a bill of materials — the gap that blocks costing and planning.",
          queries.get_bom_coverage,
          ev_fields=[("coverage_pct", "BOM coverage", "pct"),
                     ("items_missing_bom", "Items missing BOM", "count"),
                     ("total_items", "Items", "count")]),
    # Quotes & inward goods
    _make("quotes.get_summary",
          "Quotation pipeline: open quotes and value, won value, and the conversion rate for the window.",
          queries.get_quote_summary, params=("period_days",), inputs=_PERIOD,
          ev_fields=[("open_count", "Open quotes", "count"), ("open_value", "Open value", "money"),
                     ("won_value", "Won value", "money"),
                     ("conversion_rate", "Conversion", "pct")]),
    _make("grn.get_summary",
          "Goods received in the window: receipt count, inspections pending and the rejection rate.",
          queries.get_grn_summary, params=("period_days",), inputs=_PERIOD,
          ev_fields=[("received_count", "Receipts", "count"), ("pending_qir", "Pending QIR", "count"),
                     ("rejection_rate", "Rejection rate", "pct")]),
    # Meta — the tools that describe the data itself, not the business
    _make("meta.get_ingest_quality",
          "How trustworthy the underlying data is: canonical mapping coverage, issue count and the top data issues.",
          queries.get_ingest_quality, source="meta", fresh_key="",
          ev_fields=[("coverage_pct", "Mapping coverage", "pct"),
                     ("issue_count", "Issues", "count"),
                     ("total_mapped", "Rows mapped", "count")]),
    _make("meta.get_data_freshness",
          "When each source last synced and whether every pipeline is healthy — call this before trusting a number.",
          queries.get_sync_health, source="meta", fresh_key="all_healthy",
          ev_fields=[("pipeline_count", "Pipelines", "count")]),
]


def register_all() -> int:
    """Register every read tool (idempotent — skips ones already present).
    Returns the number newly registered."""
    n = 0
    for t in _TOOLS:
        if registry.get(t.name) is None:
            registry.register(t)
            n += 1
    return n


def tool_names() -> list[str]:
    return [t.name for t in _TOOLS]
