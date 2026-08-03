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

from vinayak.reasoning.engine import Evidence
from vinayak.schema import queries
from vinayak.tools import registry
from vinayak.tools.contract import Tool, ToolInput, ToolResult


# ── evidence formatting ───────────────────────────────────────────────────────
def _display(value: Any, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "money":
        v = float(value)
        a = abs(v)
        sign = "-" if v < 0 else ""
        if a >= 1e7:  return f"{sign}₹{a / 1e7:.2f} Cr"
        if a >= 1e5:  return f"{sign}₹{a / 1e5:.2f} L"
        return f"{sign}₹{a:,.0f}"
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


def _make(name: str, description: str, query_fn: Callable,
          params: tuple[str, ...] = (), inputs: dict[str, ToolInput] | None = None,
          ev_fields: list[tuple[str, str, str]] | None = None) -> Tool:
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
            quality={"data_fresh": not bool(data.get("stale", False)),
                     "source": "canonical"},
        )

    return Tool(name=name, description=description, inputs=inputs or {},
                side_effect="read", fn=fn)


_DAYS = {"days": ToolInput(int, "Trailing window in days", required=False)}
_MONTHS = {"months": ToolInput(int, "Number of months (2–24)", required=False)}

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
