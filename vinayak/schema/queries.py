"""
schema/queries.py
──────────────────
Pre-aggregated business query functions — one per dashboard panel.

Rules:
  • Every function returns a typed dict, NEVER raw rows.
  • Top-N caps are defined as constants here and enforced in every query.
  • Phase 2 AI reads ONLY from these functions — never from raw SQL.
  • Adding a new function requires both builders to agree on the schema.

Multi-tenant scoping:
  Every public query takes `company_id` (the brand / workspace key) as its
  first argument after `conn` and filters `WHERE company_id = %s`. Two brands
  syncing into the same tables therefore never see each other's rows. The
  company_id filter is always the FIRST predicate so the (company_id, …)
  composite indexes added in migration 001 are used.

Anti-context-rot guarantee:
  An AI model calling get_ar_summary() receives ~15 keys, not 5,000 rows.
  The pre-aggregation happens in SQL, not in Python, keeping it fast.

Usage:
    import psycopg2
    from vinayak.schema.queries import get_ar_summary
    conn = psycopg2.connect(DATABASE_URL)
    data = get_ar_summary(conn, "protegere")
"""
from __future__ import annotations

import logging
from datetime import datetime, date, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Top-N caps (AI safety — never return more than these) ────────────────────
MAX_CUSTOMERS  = 15
MAX_SKUS       = 20
MAX_INVOICES   = 25
MAX_VENDORS    = 10
MAX_PROCESSES  = 30
MAX_CATEGORIES = 15

# ── Staleness threshold ───────────────────────────────────────────────────────
STALE_HOURS = 25  # data older than this is flagged as stale


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def _is_stale(last_sync: datetime | None) -> bool:
    if last_sync is None:
        return True
    if last_sync.tzinfo is None:
        last_sync = last_sync.replace(tzinfo=timezone.utc)
    return (_now_utc() - last_sync).total_seconds() > STALE_HOURS * 3600


def _last_sync(conn, pipeline_name: str, company_id: str) -> datetime | None:
    """Return the most recent successful sync timestamp for a pipeline + brand."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT MAX(completed_at) FROM tz_sync_runs
               WHERE company_id = %s AND pipeline_name = %s AND status = 'success'""",
            (company_id, pipeline_name),
        )
        row = cur.fetchone()
    return row[0] if row else None


def _fmt(ts: datetime | None) -> str | None:
    return ts.isoformat() if ts else None


def _parse_date(v: Any) -> date | None:
    """Parse an ISO date string (or date) → date. Returns None on empty/bad input."""
    if not v:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    try:
        return date.fromisoformat(str(v)[:10])
    except (ValueError, TypeError):
        return None


# Internal table/column registry for the generic date-range helpers below.
# Keys are NOT user input — they are fixed identifiers, so f-string interpolation
# here is safe (no SQL injection surface).
_DATE_COLS = {
    "tz_sales_invoices":     "invoice_date",
    "tz_purchase_invoices":  "invoice_date",
    "tz_sales_orders":       "order_date",
    "tz_purchase_orders":    "po_date",
    "tz_grn_qir":            "grn_date",
    "tz_sales_quotations":   "quote_date",
    "tz_process_details":    "production_date",
}


def _date_range(conn, company_id: str, table: str) -> tuple[date | None, date | None]:
    """Min/max of the table's primary date column for a brand (data coverage)."""
    col = _DATE_COLS[table]
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT MIN({col}), MAX({col}) FROM {table} WHERE company_id = %s",  # noqa: S608
            (company_id,),
        )
        lo, hi = cur.fetchone()
    return lo, hi


def _resolve_window(
    conn, company_id: str, table: str,
    start: Any = None, end: Any = None, period_days: int = 30,
) -> dict:
    """
    Resolve an effective [start, end] window plus the brand's full data coverage.

    Behaviour:
      • Explicit start/end (range picker) are honoured when given.
      • Otherwise the window is *anchored to the latest available data*, not to
        today — so a brand whose newest invoice is in April still shows a
        populated "last 30 days" instead of an empty window.

    Returns: {start, end, data_from, data_to} (all `date` or None).
    """
    data_from, data_to = _date_range(conn, company_id, table)
    anchor = data_to or date.today()

    eff_end = _parse_date(end) or anchor
    parsed_start = _parse_date(start)
    if parsed_start is not None:
        eff_start = parsed_start
    else:
        # Clamp the lookback so a very large period_days (used as a "whole
        # dataset" sentinel) can't underflow below date.min and raise.
        lookback = min(period_days, (eff_end - date.min).days)
        eff_start = eff_end - timedelta(days=lookback)
    if eff_start > eff_end:
        eff_start, eff_end = eff_end, eff_start

    return {"start": eff_start, "end": eff_end, "data_from": data_from, "data_to": data_to}


def _window_meta(w: dict) -> dict:
    """Serialise a resolved window for the API envelope."""
    return {
        "window_from": w["start"].isoformat() if w["start"] else None,
        "window_to":   w["end"].isoformat() if w["end"] else None,
        "data_from":   w["data_from"].isoformat() if w["data_from"] else None,
        "data_to":     w["data_to"].isoformat() if w["data_to"] else None,
    }


# ── Dual-basis revenue helper (BUG 1 fix) ─────────────────────────────────────
# tz_sales_invoices / tz_purchase_invoices are LINE-LEVEL: one row per invoice
# line, and every line repeats the same header `invoice_total`. Summing
# invoice_total across lines therefore multiplies each invoice by its line count.
# We expose two correct bases instead:
#   • goods    = SUM(line_total)                  — taxable goods value
#   • invoiced = SUM of per-invoice header total  — printed invoice grand total
def _dual_window_totals(
    conn, table: str, company_id: str, s: str, e: str, date_col: str = "invoice_date",
) -> tuple[float, float]:
    """Return (goods_total, invoiced_total) for a [s, e] window on `table`."""
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
                COALESCE(SUM(line_total), 0) AS goods,
                COALESCE((
                    SELECT SUM(inv_total) FROM (
                        SELECT invoice_number, MAX(invoice_total) AS inv_total
                        FROM {table}
                        WHERE company_id = %s AND {date_col} >= %s AND {date_col} <= %s
                        GROUP BY invoice_number
                    ) d
                ), 0) AS invoiced
            FROM {table}
            WHERE company_id = %s AND {date_col} >= %s AND {date_col} <= %s
            """,  # noqa: S608 — table/date_col are fixed module identifiers
            (company_id, s, e, company_id, s, e),
        )
        goods, invoiced = cur.fetchone()
    return float(goods or 0), float(invoiced or 0)


def _sales_monthly_avg(conn, company_id: str, data_to: date | None) -> tuple[float, float]:
    """
    Average monthly sales revenue over the trailing 12 months of *available*
    data (anchored to the latest invoice, not today). Divides by the number of
    distinct months that actually have data, so it is a true average and never
    collapses to equal the period total of a 1-month window.

    Returns both bases: (goods_avg, invoiced_avg). See _dual_window_totals.
    """
    if data_to is None:
        return 0.0, 0.0
    floor = data_to - timedelta(days=365)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COALESCE(SUM(line_total), 0),
                   COUNT(DISTINCT date_trunc('month', invoice_date)),
                   COALESCE((
                       SELECT SUM(inv_total) FROM (
                           SELECT invoice_number, MAX(invoice_total) AS inv_total
                           FROM tz_sales_invoices
                           WHERE company_id = %s AND invoice_date > %s AND invoice_date <= %s
                           GROUP BY invoice_number
                       ) d
                   ), 0)
            FROM tz_sales_invoices
            WHERE company_id = %s AND invoice_date > %s AND invoice_date <= %s
            """,
            (company_id, floor.isoformat(), data_to.isoformat(),
             company_id, floor.isoformat(), data_to.isoformat()),
        )
        goods, n_months, invoiced = cur.fetchone()
    n = int(n_months or 0)
    if not n:
        return 0.0, 0.0
    return float(goods or 0) / n, float(invoiced or 0) / n


# ════════════════════════════════════════════════════════════════════════════
# STRATEGIC PANELS (daily cache)
# ════════════════════════════════════════════════════════════════════════════

def get_revenue_summary(
    conn, company_id: str, period_days: int = 30,
    start: Any = None, end: Any = None,
) -> dict:
    """
    S1 — Revenue KPIs for a window (default: trailing `period_days` anchored to
    the latest invoice date; or an explicit [start, end] range).

    Returns: period_total, invoice_count, customer_count, avg_invoice_value,
             monthly_avg (trailing-12mo true average), ytd_total, plus
             window_from/window_to/data_from/data_to.
    """
    w = _resolve_window(conn, company_id, "tz_sales_invoices", start, end, period_days)
    s, e = w["start"].isoformat(), w["end"].isoformat()
    # BUG 1 fix: compute both the goods (SUM line_total) and the invoiced
    # (per-invoice header) bases instead of the line-multiplied SUM(invoice_total).
    period_goods, period_invoiced = _dual_window_totals(
        conn, "tz_sales_invoices", company_id, s, e)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(DISTINCT invoice_number)   AS invoice_count,
                COUNT(DISTINCT customer_code)    AS customer_count
            FROM tz_sales_invoices
            WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
        """, (company_id, s, e))
        row = cur.fetchone()

        # YTD anchored to the latest data year (not necessarily the wall-clock year).
        anchor_year = (w["data_to"] or date.today()).year
        ystart, yend = date(anchor_year, 1, 1).isoformat(), date(anchor_year, 12, 31).isoformat()
    ytd_goods, ytd_invoiced = _dual_window_totals(
        conn, "tz_sales_invoices", company_id, ystart, yend)

    invoice_count = int(row[0] or 0)
    monthly_goods, monthly_invoiced = _sales_monthly_avg(conn, company_id, w["data_to"])
    ls = _last_sync(conn, "sales_invoices", company_id)
    return {
        "period_days":           period_days,
        # `period_total` keeps the goods basis (matches SKU/line tables & charts).
        "period_total":          period_goods,
        "period_total_goods":    period_goods,
        "period_total_invoiced": period_invoiced,
        "invoice_count":         invoice_count,
        "customer_count":        int(row[1] or 0),
        "avg_invoice_value":     (period_invoiced / invoice_count) if invoice_count else 0.0,
        "monthly_avg":           monthly_goods,
        "monthly_avg_invoiced":  monthly_invoiced,
        "ytd_total":             ytd_goods,
        "ytd_invoiced":          ytd_invoiced,
        "ytd_year":              anchor_year,
        **_window_meta(w),
        "last_synced_at":        _fmt(ls),
        "stale":                 _is_stale(ls),
    }


def get_revenue_trend(conn, company_id: str, months: int = 6) -> dict:
    """
    S2 — Monthly revenue trend (bar/line chart data), anchored to the latest
    available data so the chart is never empty. Gap-fills missing months with 0.
    Returns: months list [{month, revenue, invoice_count}]
    """
    data_from, data_to = _date_range(conn, company_id, "tz_sales_invoices")
    anchor = data_to or date.today()
    # Compute the first day of the window's earliest month, `months` back.
    y, m = anchor.year, anchor.month
    m -= (months - 1)
    while m <= 0:
        m += 12
        y -= 1
    start_month = date(y, m, 1)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                TO_CHAR(invoice_date, 'YYYY-MM') AS month,
                COALESCE(SUM(line_total), 0)     AS revenue,
                COUNT(DISTINCT invoice_number)   AS invoice_count
            FROM tz_sales_invoices
            WHERE company_id = %s AND invoice_date >= %s
            GROUP BY 1 ORDER BY 1
        """, (company_id, start_month.isoformat()))
        found = {r[0]: (float(r[1]), int(r[2])) for r in cur.fetchall()}

    # Gap-fill every month in the window so the chart x-axis is continuous.
    series = []
    cy, cm = start_month.year, start_month.month
    for _ in range(months):
        key = f"{cy:04d}-{cm:02d}"
        rev, cnt = found.get(key, (0.0, 0))
        series.append({"month": key, "revenue": rev, "invoice_count": cnt})
        cm += 1
        if cm > 12:
            cm = 1
            cy += 1

    ls = _last_sync(conn, "sales_invoices", company_id)
    return {
        "months": series,
        "data_from": data_from.isoformat() if data_from else None,
        "data_to":   data_to.isoformat() if data_to else None,
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_revenue_daily(
    conn, company_id: str, period_days: int = 90,
    start: Any = None, end: Any = None,
) -> dict:
    """
    S2b — Daily revenue series for a line chart (default trailing `period_days`
    anchored to latest data, or explicit range). Gap-fills missing days with 0.
    Returns: days list [{date, revenue, invoice_count}]
    """
    w = _resolve_window(conn, company_id, "tz_sales_invoices", start, end, period_days)
    s, e = w["start"], w["end"]
    with conn.cursor() as cur:
        cur.execute("""
            SELECT invoice_date,
                   COALESCE(SUM(line_total), 0),
                   COUNT(DISTINCT invoice_number)
            FROM tz_sales_invoices
            WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
            GROUP BY invoice_date
        """, (company_id, s.isoformat(), e.isoformat()))
        found = {r[0]: (float(r[1]), int(r[2])) for r in cur.fetchall()}

    days = []
    cur_d = s
    # Cap at ~370 points to keep the payload small.
    guard = 0
    while cur_d <= e and guard < 400:
        rev, cnt = found.get(cur_d, (0.0, 0))
        days.append({"date": cur_d.isoformat(), "revenue": rev, "invoice_count": cnt})
        cur_d += timedelta(days=1)
        guard += 1

    ls = _last_sync(conn, "sales_invoices", company_id)
    return {
        "days": days,
        **_window_meta(w),
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_customer_concentration(
    conn, company_id: str, period_days: int = 30,
    start: Any = None, end: Any = None,
) -> dict:
    """
    S3 — Customer revenue concentration (doughnut chart).
    Returns top 5 customers + 'Others' slice for the resolved window.
    """
    w = _resolve_window(conn, company_id, "tz_sales_invoices", start, end, period_days)
    s, e = w["start"].isoformat(), w["end"].isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT customer_name, COALESCE(SUM(line_total), 0) AS revenue
            FROM tz_sales_invoices
            WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
            GROUP BY customer_name
            ORDER BY revenue DESC
            LIMIT 5
        """, (company_id, s, e))
        top5 = cur.fetchall()

        cur.execute("""
            SELECT COALESCE(SUM(line_total), 0)
            FROM tz_sales_invoices
            WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
        """, (company_id, s, e))
        total = float(cur.fetchone()[0] or 0)

    top5_total = sum(float(r[1]) for r in top5)
    others = max(0.0, total - top5_total)
    slices = [{"name": r[0], "value": float(r[1])} for r in top5]
    if others > 0:
        slices.append({"name": "Others", "value": others})

    ls = _last_sync(conn, "sales_invoices", company_id)
    return {
        "total": total,
        "slices": slices,
        **_window_meta(w),
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_top_customers_revenue(
    conn, company_id: str, period_days: int = 30,
    start: Any = None, end: Any = None,
) -> dict:
    """
    S4 — Top N customers by revenue for the resolved window.
    Returns: customers list [{customer_name, revenue, invoice_count, pct_of_total}]
    """
    w = _resolve_window(conn, company_id, "tz_sales_invoices", start, end, period_days)
    s, e = w["start"].isoformat(), w["end"].isoformat()
    with conn.cursor() as cur:
        cur.execute(f"""
            WITH totals AS (
                SELECT SUM(line_total) AS grand_total
                FROM tz_sales_invoices
                WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
            )
            SELECT
                customer_name,
                COALESCE(SUM(line_total), 0) AS revenue,
                COUNT(DISTINCT invoice_number)  AS invoice_count,
                ROUND(
                    100.0 * SUM(line_total) / NULLIF((SELECT grand_total FROM totals), 0),
                    1
                ) AS pct
            FROM tz_sales_invoices
            WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
            GROUP BY customer_name
            ORDER BY revenue DESC
            LIMIT {MAX_CUSTOMERS}
        """, (company_id, s, e, company_id, s, e))
        rows = cur.fetchall()

    ls = _last_sync(conn, "sales_invoices", company_id)
    return {
        "period_days": period_days,
        "customers": [
            {"customer_name": r[0], "revenue": float(r[1]),
             "invoice_count": int(r[2]), "pct_of_total": float(r[3] or 0)}
            for r in rows
        ],
        **_window_meta(w),
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_top_skus_revenue(
    conn, company_id: str, period_days: int = 30,
    start: Any = None, end: Any = None,
) -> dict:
    """
    S5 — Top N SKUs by revenue for the resolved window.
    Returns: skus list [{sku_code, sku_name, revenue, quantity, invoice_count}]
    """
    w = _resolve_window(conn, company_id, "tz_sales_invoices", start, end, period_days)
    s, e = w["start"].isoformat(), w["end"].isoformat()
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                sku_code,
                MAX(sku_name) AS sku_name,
                COALESCE(SUM(line_total), 0) AS revenue,
                COALESCE(SUM(quantity), 0)   AS quantity,
                COUNT(DISTINCT invoice_number) AS invoice_count
            FROM tz_sales_invoices
            WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
              AND sku_code IS NOT NULL
            GROUP BY sku_code
            ORDER BY revenue DESC
            LIMIT {MAX_SKUS}
        """, (company_id, s, e))
        rows = cur.fetchall()

    ls = _last_sync(conn, "sales_invoices", company_id)
    return {
        "period_days": period_days,
        "skus": [
            {"sku_code": r[0], "sku_name": r[1], "revenue": float(r[2]),
             "quantity": float(r[3]), "invoice_count": int(r[4])}
            for r in rows
        ],
        **_window_meta(w),
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_inventory_summary(conn, company_id: str) -> dict:
    """
    S6 — Inventory KPIs.
    Returns: total_value, total_skus, negative_stock_count, warehouse_count
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COALESCE(SUM(total_value), 0) AS total_value,
                COUNT(DISTINCT sku_code)      AS total_skus,
                COUNT(*) FILTER (WHERE quantity < 0) AS negative_stock_count,
                COUNT(DISTINCT warehouse)     AS warehouse_count
            FROM tz_inventory_valuation
            WHERE company_id = %s
        """, (company_id,))
        row = cur.fetchone()

    ls = _last_sync(conn, "inventory_valuation", company_id)
    return {
        "total_value":          float(row[0] or 0),
        "total_skus":           int(row[1] or 0),
        "negative_stock_count": int(row[2] or 0),
        "warehouse_count":      int(row[3] or 0),
        "last_synced_at":       _fmt(ls),
        "stale":                _is_stale(ls),
    }


def get_inventory_by_category(conn, company_id: str) -> dict:
    """
    S7 — Stock value by product category.
    Returns: categories list [{category, total_value, sku_count}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                COALESCE(category, 'Uncategorised') AS category,
                COALESCE(SUM(total_value), 0)        AS total_value,
                COUNT(DISTINCT sku_code)             AS sku_count
            FROM tz_inventory_valuation
            WHERE company_id = %s
            GROUP BY 1
            ORDER BY total_value DESC
            LIMIT {MAX_CATEGORIES}
        """, (company_id,))
        rows = cur.fetchall()

    ls = _last_sync(conn, "inventory_valuation", company_id)
    return {
        "categories": [
            {"category": r[0], "total_value": float(r[1]), "sku_count": int(r[2])}
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_top_stock_holdings(conn, company_id: str) -> dict:
    """
    S8 — Highest-value SKUs in stock (potential working-capital lock-up).
    Returns: skus list [{sku_code, sku_name, category, quantity, total_value}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT sku_code, sku_name, category, quantity, total_value
            FROM tz_inventory_valuation
            WHERE company_id = %s AND quantity > 0
            ORDER BY total_value DESC
            LIMIT {MAX_SKUS}
        """, (company_id,))
        rows = cur.fetchall()

    ls = _last_sync(conn, "inventory_valuation", company_id)
    return {
        "skus": [
            {"sku_code": r[0], "sku_name": r[1], "category": r[2],
             "quantity": float(r[3] or 0), "total_value": float(r[4] or 0)}
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def _purchase_monthly_avg(conn, company_id: str) -> tuple[float, float]:
    """
    Average monthly purchase spend over the trailing 12 months of *available*
    data (anchored to the latest invoice). Divides by the number of distinct
    months that actually have data, so it is a true average and never collapses
    to equal a 1-month period total.

    Returns both bases: (goods_avg, invoiced_avg). See _dual_window_totals.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT MAX(invoice_date) FROM tz_purchase_invoices WHERE company_id = %s",
            (company_id,),
        )
        data_to = cur.fetchone()[0]
        if data_to is None:
            return 0.0, 0.0
        floor = data_to - timedelta(days=365)
        cur.execute(
            """
            SELECT COALESCE(SUM(line_total), 0),
                   COUNT(DISTINCT date_trunc('month', invoice_date)),
                   COALESCE((
                       SELECT SUM(inv_total) FROM (
                           SELECT invoice_number, MAX(invoice_total) AS inv_total
                           FROM tz_purchase_invoices
                           WHERE company_id = %s AND invoice_date > %s AND invoice_date <= %s
                           GROUP BY invoice_number
                       ) d
                   ), 0)
            FROM tz_purchase_invoices
            WHERE company_id = %s AND invoice_date > %s AND invoice_date <= %s
            """,
            (company_id, floor.isoformat(), data_to.isoformat(),
             company_id, floor.isoformat(), data_to.isoformat()),
        )
        goods, n_months, invoiced = cur.fetchone()
    n = int(n_months or 0)
    if not n:
        return 0.0, 0.0
    return float(goods or 0) / n, float(invoiced or 0) / n


def get_purchases_summary(conn, company_id: str, period_days: int = 30) -> dict:
    """
    S9 — Purchase KPIs.
    Returns: period_spend (+ goods/invoiced bases), monthly_avg, vendor_count,
             invoice_count, overdue_po_count.
    """
    # BUG 2 fix: anchor the window to the latest available data, not today, so
    # this lines up with the revenue panels even when sync data is not current.
    w = _resolve_window(conn, company_id, "tz_purchase_invoices", None, None, period_days)
    s, e = w["start"].isoformat(), w["end"].isoformat()
    # BUG 1 fix: dual basis instead of line-multiplied SUM(invoice_total).
    period_goods, period_invoiced = _dual_window_totals(
        conn, "tz_purchase_invoices", company_id, s, e)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(DISTINCT vendor_name)     AS vendor_count,
                COUNT(DISTINCT invoice_number)  AS invoice_count
            FROM tz_purchase_invoices
            WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
        """, (company_id, s, e))
        row = cur.fetchone()

        # BUG 3 fix: status is mixed-case in TranzAct — compare case-insensitively.
        cur.execute("""
            SELECT COUNT(*) FROM tz_purchase_orders
            WHERE company_id = %s
              AND expected_date < CURRENT_DATE
              AND status NOT ILIKE 'received'
              AND status NOT ILIKE 'cancelled'
        """, (company_id,))
        overdue_pos = cur.fetchone()[0]

    monthly_goods, monthly_invoiced = _purchase_monthly_avg(conn, company_id)
    ls = _last_sync(conn, "purchase_invoices", company_id)
    return {
        "period_days":          period_days,
        "period_spend":         period_goods,
        "period_spend_goods":   period_goods,
        "period_spend_invoiced": period_invoiced,
        "monthly_avg":          monthly_goods,
        "monthly_avg_invoiced": monthly_invoiced,
        "vendor_count":         int(row[0] or 0),
        "invoice_count":        int(row[1] or 0),
        "overdue_po_count":     int(overdue_pos or 0),
        **_window_meta(w),
        "last_synced_at":       _fmt(ls),
        "stale":                _is_stale(ls),
    }


def get_top_vendors_spend(conn, company_id: str, period_days: int = 30) -> dict:
    """
    S10 — Top N vendors by purchase spend.
    Returns: vendors list [{vendor_name, spend, invoice_count, pct_of_total}]
    """
    # BUG 2 fix: anchor to latest data; BUG 1 fix: line_total basis (goods).
    w = _resolve_window(conn, company_id, "tz_purchase_invoices", None, None, period_days)
    s, e = w["start"].isoformat(), w["end"].isoformat()
    with conn.cursor() as cur:
        cur.execute(f"""
            WITH totals AS (
                SELECT SUM(line_total) AS grand_total
                FROM tz_purchase_invoices
                WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
            )
            SELECT
                vendor_name,
                COALESCE(SUM(line_total), 0) AS spend,
                COUNT(DISTINCT invoice_number)  AS invoice_count,
                ROUND(
                    100.0 * SUM(line_total) / NULLIF((SELECT grand_total FROM totals), 0),
                    1
                ) AS pct
            FROM tz_purchase_invoices
            WHERE company_id = %s AND invoice_date >= %s AND invoice_date <= %s
            GROUP BY vendor_name
            ORDER BY spend DESC
            LIMIT {MAX_VENDORS}
        """, (company_id, s, e, company_id, s, e))
        rows = cur.fetchall()

    ls = _last_sync(conn, "purchase_invoices", company_id)
    return {
        "period_days": period_days,
        "vendors": [
            {"vendor_name": r[0], "spend": float(r[1]),
             "invoice_count": int(r[2]), "pct_of_total": float(r[3] or 0)}
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_production_summary(conn, company_id: str, period_days: int = 30) -> dict:
    """
    S11 — Production KPIs.
    Returns: fg_produced, rejected, reject_rate_pct, wip_count, completed_count
    """
    # BUG 2 fix: anchor to latest available production data, not today.
    w = _resolve_window(conn, company_id, "tz_process_details", None, None, period_days)
    s, e = w["start"].isoformat(), w["end"].isoformat()
    with conn.cursor() as cur:
        # TranzAct stores status_text as 'WIP' / 'Pending' / 'Planned' (mixed
        # case, and there is no literal 'completed' state). Match case-insensitively
        # and count distinct work orders, not process rows, so "WIP Jobs" is a job
        # count rather than an operation count. A job is treated as completed once
        # its produced quantity meets or exceeds the planned quantity.
        cur.execute("""
            SELECT
                COALESCE(SUM(produced_qty), 0)  AS fg_produced,
                COALESCE(SUM(rejected_qty), 0)  AS rejected,
                COUNT(DISTINCT work_order_number)
                    FILTER (WHERE status ILIKE 'wip')                       AS wip_count,
                COUNT(DISTINCT work_order_number)
                    FILTER (WHERE status ILIKE 'completed'
                                OR status ILIKE 'closed'
                                OR (planned_qty > 0 AND produced_qty >= planned_qty)) AS completed_count
            FROM tz_process_details
            WHERE company_id = %s AND production_date >= %s AND production_date <= %s
        """, (company_id, s, e))
        row = cur.fetchone()

    fg = float(row[0] or 0)
    rej = float(row[1] or 0)
    reject_rate = round(100.0 * rej / (fg + rej), 2) if (fg + rej) > 0 else 0.0

    ls = _last_sync(conn, "process_details", company_id)
    return {
        "period_days":      period_days,
        "fg_produced":      fg,
        "rejected":         rej,
        "reject_rate_pct":  reject_rate,
        "wip_count":        int(row[2] or 0),
        "completed_count":  int(row[3] or 0),
        "last_synced_at":   _fmt(ls),
        "stale":            _is_stale(ls),
    }


def get_quote_summary(conn, company_id: str, period_days: int = 30) -> dict:
    """
    S13 — Sales quotation pipeline KPIs.

    A quote counts as won once it converts to an order (converted_to_order) or
    its status explicitly says so. Everything not won/lost/cancelled is open.
    Returns: open_count, open_value, won_count, won_value, conversion_rate.
    """
    # BUG 2 fix: anchor to latest available quotation data, not today.
    w = _resolve_window(conn, company_id, "tz_sales_quotations", None, None, period_days)
    s, e = w["start"].isoformat(), w["end"].isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) FILTER (
                    WHERE converted_to_order OR status ILIKE 'won' OR status ILIKE 'accepted'
                ) AS won_count,
                COALESCE(SUM(quoted_value) FILTER (
                    WHERE converted_to_order OR status ILIKE 'won' OR status ILIKE 'accepted'
                ), 0) AS won_value,
                COUNT(*) FILTER (
                    WHERE NOT converted_to_order
                      AND status NOT ILIKE 'won' AND status NOT ILIKE 'accepted'
                      AND status NOT ILIKE 'lost' AND status NOT ILIKE 'rejected'
                      AND status NOT ILIKE 'cancelled'
                ) AS open_count,
                COALESCE(SUM(quoted_value) FILTER (
                    WHERE NOT converted_to_order
                      AND status NOT ILIKE 'won' AND status NOT ILIKE 'accepted'
                      AND status NOT ILIKE 'lost' AND status NOT ILIKE 'rejected'
                      AND status NOT ILIKE 'cancelled'
                ), 0) AS open_value,
                COUNT(*) AS total_count
            FROM tz_sales_quotations
            WHERE company_id = %s AND quote_date >= %s AND quote_date <= %s
        """, (company_id, s, e))
        row = cur.fetchone()

    won_count = int(row[0] or 0)
    total = int(row[4] or 0)
    conversion = (won_count / total) if total else 0.0

    ls = _last_sync(conn, "sales_quotations", company_id)
    return {
        "period_days":     period_days,
        "open_count":      int(row[2] or 0),
        "open_value":      float(row[3] or 0),
        "won_count":       won_count,
        "won_value":       float(row[1] or 0),
        "conversion_rate": conversion,
        "last_synced_at":  _fmt(ls),
        "stale":           _is_stale(ls),
    }


def get_grn_summary(conn, company_id: str, period_days: int = 30) -> dict:
    """
    S14 — Goods Received Note KPIs.

    Source report 34 carries quantities but no monetary value, so total_value is
    0. pending_qir = GRN lines received but not yet inspected (no rejection
    decision recorded). rejection_rate = rejected / received.
    Returns: received_count, total_value, pending_qir, rejection_rate.
    """
    # BUG 2 fix: anchor to latest available GRN data, not today.
    w = _resolve_window(conn, company_id, "tz_grn_qir", None, None, period_days)
    s, e = w["start"].isoformat(), w["end"].isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(DISTINCT grn_number)              AS received_count,
                COALESCE(SUM(received_qty), 0)          AS total_received,
                COALESCE(SUM(rejected_qty), 0)          AS total_rejected,
                COUNT(*) FILTER (WHERE rejected_qty IS NULL) AS pending_qir
            FROM tz_grn_qir
            WHERE company_id = %s AND grn_date >= %s AND grn_date <= %s
        """, (company_id, s, e))
        row = cur.fetchone()

    received = float(row[1] or 0)
    rejected = float(row[2] or 0)
    rejection_rate = (rejected / received) if received > 0 else 0.0

    ls = _last_sync(conn, "grn_qir", company_id)
    return {
        "period_days":    period_days,
        "received_count": int(row[0] or 0),
        "total_value":    0.0,
        "pending_qir":    int(row[3] or 0),
        "rejection_rate": rejection_rate,
        "last_synced_at": _fmt(ls),
        "stale":          _is_stale(ls),
    }


def get_bom_coverage(conn, company_id: str) -> dict:
    """
    S15 — BOM / routing coverage.

    Measures what fraction of manufactured SKUs (those appearing in production
    process details) have a defined process routing (report 86).
    Returns: total_items, items_with_bom, coverage_pct, items_missing_bom.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(DISTINCT pd.sku_code)
            FROM tz_process_details pd
            WHERE pd.company_id = %s AND pd.sku_code IS NOT NULL
        """, (company_id,))
        total_items = int(cur.fetchone()[0] or 0)

        cur.execute("""
            SELECT COUNT(DISTINCT pd.sku_code)
            FROM tz_process_details pd
            WHERE pd.company_id = %s AND pd.sku_code IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM tz_process_routing pr
                  WHERE pr.company_id = pd.company_id AND pr.sku_code = pd.sku_code
              )
        """, (company_id,))
        items_with_bom = int(cur.fetchone()[0] or 0)

    coverage = (items_with_bom / total_items) if total_items else 0.0
    ls = _last_sync(conn, "process_routing", company_id)
    return {
        "total_items":       total_items,
        "items_with_bom":    items_with_bom,
        "coverage_pct":      round(coverage * 100, 1),
        "items_missing_bom": total_items - items_with_bom,
        "last_synced_at":    _fmt(ls),
        "stale":             _is_stale(ls),
    }


def get_order_book_summary(conn, company_id: str) -> dict:
    """
    S12 — Sales order book KPIs.
    Returns: open_order_count, open_order_value, dispatched_pct, overdue_count
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE LOWER(status) NOT IN ('dispatched', 'cancelled')) AS open_count,
                COALESCE(SUM(order_value) FILTER (WHERE LOWER(status) NOT IN ('dispatched','cancelled')), 0) AS open_value,
                COUNT(*) FILTER (WHERE LOWER(status) = 'dispatched') AS dispatched_count,
                COUNT(*) AS total_count,
                COUNT(*) FILTER (
                    WHERE delivery_date < CURRENT_DATE
                    AND LOWER(status) NOT IN ('dispatched', 'cancelled')
                ) AS overdue_count
            FROM tz_sales_orders
            WHERE company_id = %s
        """, (company_id,))
        row = cur.fetchone()

    total = int(row[3] or 0)
    dispatched = int(row[2] or 0)
    dispatched_pct = round(100.0 * dispatched / total, 1) if total > 0 else 0.0

    ls = _last_sync(conn, "sales_orders", company_id)
    return {
        "open_order_count":  int(row[0] or 0),
        "open_order_value":  float(row[1] or 0),
        "dispatched_pct":    dispatched_pct,
        "overdue_count":     int(row[4] or 0),
        "last_synced_at":    _fmt(ls),
        "stale":             _is_stale(ls),
    }


# ════════════════════════════════════════════════════════════════════════════
# OPERATIONAL PANELS (hourly cache — Sandeep's morning alerts)
# ════════════════════════════════════════════════════════════════════════════

def get_ar_summary(conn, company_id: str) -> dict:
    """
    O1 — AR aging buckets + overdue invoice list.
    Returns: aging_buckets, overdue_count, overdue_value, top_exposures
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                aging_bucket,
                COUNT(*)                            AS count,
                COALESCE(SUM(outstanding_amount), 0) AS value
            FROM tz_ar_aging
            WHERE company_id = %s
            GROUP BY aging_bucket
            ORDER BY aging_bucket
        """, (company_id,))
        buckets = cur.fetchall()

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE days_overdue > 0) AS overdue_count,
                COALESCE(SUM(outstanding_amount) FILTER (WHERE days_overdue > 0), 0) AS overdue_value,
                COALESCE(SUM(outstanding_amount), 0) AS total_outstanding
            FROM tz_ar_aging
            WHERE company_id = %s
        """, (company_id,))
        summary = cur.fetchone()

        cur.execute(f"""
            SELECT
                customer_name,
                COALESCE(SUM(outstanding_amount), 0) AS outstanding,
                MAX(days_overdue)                    AS oldest_days
            FROM tz_ar_aging
            WHERE company_id = %s
            GROUP BY customer_name
            ORDER BY outstanding DESC
            LIMIT {MAX_CUSTOMERS}
        """, (company_id,))
        exposures = cur.fetchall()

    ls = _last_sync(conn, "ar_aging", company_id)
    return {
        "aging_buckets": [
            {"bucket": r[0], "count": int(r[1]), "value": float(r[2])}
            for r in buckets
        ],
        "overdue_count":     int(summary[0] or 0),
        "overdue_value":     float(summary[1] or 0),
        "total_outstanding": float(summary[2] or 0),
        "top_exposures": [
            {"customer_name": r[0], "outstanding": float(r[1]),
             "oldest_days": int(r[2] or 0)}
            for r in exposures
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_ar_customer_exposure(conn, company_id: str) -> dict:
    """
    O2 — AR exposure per customer with oldest invoice age.
    Returns: customers list [{customer_name, outstanding, invoice_count, oldest_days, overdue_value}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                customer_name,
                COALESCE(SUM(outstanding_amount), 0)                            AS outstanding,
                COUNT(*)                                                         AS invoice_count,
                MAX(days_overdue)                                                AS oldest_days,
                COALESCE(SUM(outstanding_amount) FILTER (WHERE days_overdue > 0), 0) AS overdue_value
            FROM tz_ar_aging
            WHERE company_id = %s
            GROUP BY customer_name
            ORDER BY outstanding DESC
            LIMIT {MAX_CUSTOMERS}
        """, (company_id,))
        rows = cur.fetchall()

    ls = _last_sync(conn, "ar_aging", company_id)
    return {
        "customers": [
            {
                "customer_name": r[0],
                "outstanding":   float(r[1]),
                "invoice_count": int(r[2]),
                "oldest_days":   int(r[3] or 0),
                "overdue_value": float(r[4]),
            }
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_overdue_pos(conn, company_id: str) -> dict:
    """
    O3 — Overdue purchase orders (past expected date, not received).
    Returns: pos list [{po_number, vendor_name, item_name, pending_qty, po_value,
                        expected_date, days_overdue}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                po_number,
                vendor_name,
                item_name,
                pending_qty,
                po_value,
                expected_date,
                (CURRENT_DATE - expected_date) AS days_overdue
            FROM tz_purchase_orders
            WHERE company_id = %s
              AND expected_date < CURRENT_DATE
              AND LOWER(status) NOT IN ('received', 'cancelled')
            ORDER BY days_overdue DESC
            LIMIT {MAX_INVOICES}
        """, (company_id,))
        rows = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(po_value), 0)
            FROM tz_purchase_orders
            WHERE company_id = %s
              AND expected_date < CURRENT_DATE
              AND LOWER(status) NOT IN ('received', 'cancelled')
        """, (company_id,))
        totals = cur.fetchone()

    ls = _last_sync(conn, "purchase_orders", company_id)
    return {
        "total_overdue_count": int(totals[0] or 0),
        "total_value_at_risk": float(totals[1] or 0),
        "pos": [
            {
                "po_number":    r[0],
                "vendor_name":  r[1],
                "item_name":    r[2],
                "pending_qty":  float(r[3] or 0),
                "po_value":     float(r[4] or 0),
                "expected_date": str(r[5]) if r[5] else None,
                "days_overdue": int(r[6] or 0),
            }
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_open_pos(conn, company_id: str) -> dict:
    """
    O3b — Open purchase order book.

    Distinguishes two figures that must NOT be conflated:
      • open  = every PO not yet received/cancelled (regardless of date)
      • overdue = the subset of open POs whose expected_date is in the past

    Returns: open_count, open_value, overdue_count, overdue_value,
             by_vendor [{vendor_name, count, value}] (top vendors by open value)
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*)                                                       AS open_count,
                COALESCE(SUM(po_value), 0)                                     AS open_value,
                COUNT(*) FILTER (WHERE expected_date < CURRENT_DATE)           AS overdue_count,
                COALESCE(SUM(po_value) FILTER (WHERE expected_date < CURRENT_DATE), 0) AS overdue_value
            FROM tz_purchase_orders
            WHERE company_id = %s
              AND LOWER(status) NOT IN ('received', 'cancelled')
        """, (company_id,))
        totals = cur.fetchone()

        cur.execute(f"""
            SELECT vendor_name, COUNT(*), COALESCE(SUM(po_value), 0)
            FROM tz_purchase_orders
            WHERE company_id = %s
              AND LOWER(status) NOT IN ('received', 'cancelled')
            GROUP BY vendor_name
            ORDER BY COALESCE(SUM(po_value), 0) DESC
            LIMIT {MAX_VENDORS}
        """, (company_id,))
        vendors = cur.fetchall()

    ls = _last_sync(conn, "purchase_orders", company_id)
    return {
        "open_count":     int(totals[0] or 0),
        "open_value":     float(totals[1] or 0),
        "overdue_count":  int(totals[2] or 0),
        "overdue_value":  float(totals[3] or 0),
        "by_vendor": [
            {"vendor_name": v[0], "count": int(v[1] or 0), "value": float(v[2] or 0)}
            for v in vendors
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_production_wip(conn, company_id: str) -> dict:
    """
    O4 — WIP and production status breakdown.
    Returns: status_breakdown [{status, count, planned_qty, produced_qty}],
             wip_items list (most recent WIP work orders)
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                status,
                COUNT(*)                       AS count,
                COALESCE(SUM(planned_qty), 0)  AS planned_qty,
                COALESCE(SUM(produced_qty), 0) AS produced_qty
            FROM tz_process_details
            WHERE company_id = %s
            GROUP BY status
            ORDER BY count DESC
        """, (company_id,))
        breakdown = cur.fetchall()

        cur.execute(f"""
            SELECT
                work_order_number,
                sku_name,
                process_name,
                planned_qty,
                produced_qty,
                production_date
            FROM tz_process_details
            WHERE company_id = %s AND status ILIKE 'wip'
            ORDER BY production_date DESC
            LIMIT {MAX_PROCESSES}
        """, (company_id,))
        wip = cur.fetchall()

    ls = _last_sync(conn, "process_details", company_id)
    return {
        "status_breakdown": [
            {"status": r[0], "count": int(r[1]),
             "planned_qty": float(r[2]), "produced_qty": float(r[3])}
            for r in breakdown
        ],
        "wip_items": [
            {
                "work_order_number": r[0],
                "sku_name":          r[1],
                "process_name":      r[2],
                "planned_qty":       float(r[3] or 0),
                "produced_qty":      float(r[4] or 0),
                "production_date":   str(r[5]) if r[5] else None,
            }
            for r in wip
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


def get_overdue_orders(conn, company_id: str) -> dict:
    """
    O5 — Overdue order confirmations (past delivery date, not dispatched).
    Returns: orders list [{order_number, customer_name, sku_name, pending_qty,
                           order_value, delivery_date, days_overdue}]
    """
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT
                order_number,
                customer_name,
                sku_name,
                pending_qty,
                order_value,
                delivery_date,
                (CURRENT_DATE - delivery_date) AS days_overdue
            FROM tz_sales_orders
            WHERE company_id = %s
              AND delivery_date < CURRENT_DATE
              AND LOWER(status) NOT IN ('dispatched', 'cancelled')
            ORDER BY days_overdue DESC
            LIMIT {MAX_INVOICES}
        """, (company_id,))
        rows = cur.fetchall()

        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(order_value), 0)
            FROM tz_sales_orders
            WHERE company_id = %s
              AND delivery_date < CURRENT_DATE
              AND LOWER(status) NOT IN ('dispatched', 'cancelled')
        """, (company_id,))
        totals = cur.fetchone()

    ls = _last_sync(conn, "sales_orders", company_id)
    return {
        "total_overdue_count": int(totals[0] or 0),
        "total_value":         float(totals[1] or 0),
        "orders": [
            {
                "order_number":  r[0],
                "customer_name": r[1],
                "sku_name":      r[2],
                "pending_qty":   float(r[3] or 0),
                "order_value":   float(r[4] or 0),
                "delivery_date": str(r[5]) if r[5] else None,
                "days_overdue":  int(r[6] or 0),
            }
            for r in rows
        ],
        "last_synced_at": _fmt(ls),
        "stale": _is_stale(ls),
    }


# ════════════════════════════════════════════════════════════════════════════
# ROW-LEVEL DETAIL LISTS (server-side date range + search + pagination)
# ════════════════════════════════════════════════════════════════════════════

# Pagination guard rails.
MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 25


def _clamp_page(page: Any, page_size: Any) -> tuple[int, int]:
    try:
        p = max(0, int(page))
    except (TypeError, ValueError):
        p = 0
    try:
        ps = int(page_size)
    except (TypeError, ValueError):
        ps = DEFAULT_PAGE_SIZE
    ps = max(1, min(MAX_PAGE_SIZE, ps))
    return p, ps


def get_sales_invoices_list(
    conn, company_id: str,
    start: Any = None, end: Any = None, search: Any = None,
    page: int = 0, page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "invoice_date", direction: str = "desc",
) -> dict:
    """
    Detail S-list — paginated sales-invoice lines for a brand.

    Filters: [start, end] on invoice_date (defaults to full data range), and a
    free-text `search` over customer_name / invoice_number / sku_name / sku_code.
    Returns: rows, total_count, page, page_size, page_count, window/data meta.
    """
    w = _resolve_window(conn, company_id, "tz_sales_invoices", start, end,
                        period_days=10**6)  # huge default → full data span when unset
    # If neither bound supplied, span the whole dataset.
    if not start and not end and w["data_from"]:
        w["start"] = w["data_from"]
    s, e = w["start"].isoformat(), w["end"].isoformat()
    p, ps = _clamp_page(page, page_size)

    where = ["company_id = %s", "invoice_date >= %s", "invoice_date <= %s"]
    params: list[Any] = [company_id, s, e]
    if search:
        where.append(
            "(customer_name ILIKE %s OR invoice_number ILIKE %s "
            "OR sku_name ILIKE %s OR sku_code ILIKE %s)"
        )
        like = f"%{search}%"
        params += [like, like, like, like]
    where_sql = " AND ".join(where)

    sort_cols = {
        "invoice_date": "invoice_date", "invoice_total": "invoice_total",
        "line_total": "line_total", "customer_name": "customer_name",
        "quantity": "quantity",
    }
    order_col = sort_cols.get(sort, "invoice_date")
    order_dir = "ASC" if str(direction).lower() == "asc" else "DESC"

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*), COALESCE(SUM(line_total),0) "  # noqa: S608
            f"FROM tz_sales_invoices WHERE {where_sql}",
            params,
        )
        total_count, filtered_total = cur.fetchone()

        cur.execute(
            f"""
            SELECT invoice_date, invoice_number, customer_name, sku_code, sku_name,
                   quantity, unit_price, line_total, invoice_total, payment_status, salesperson
            FROM tz_sales_invoices
            WHERE {where_sql}
            ORDER BY {order_col} {order_dir} NULLS LAST, invoice_number
            LIMIT %s OFFSET %s
            """,  # noqa: S608
            params + [ps, p * ps],
        )
        rows = cur.fetchall()

    ls = _last_sync(conn, "sales_invoices", company_id)
    return {
        "rows": [
            {
                "invoice_date":   str(r[0]) if r[0] else None,
                "invoice_number": r[1],
                "customer_name":  r[2],
                "sku_code":       r[3],
                "sku_name":       r[4],
                "quantity":       float(r[5] or 0),
                "unit_price":     float(r[6] or 0),
                "line_total":     float(r[7] or 0),
                "invoice_total":  float(r[8] or 0),
                "payment_status": r[9],
                "salesperson":    r[10],
            }
            for r in rows
        ],
        "total_count":   int(total_count or 0),
        "filtered_total": float(filtered_total or 0),
        "page":          p,
        "page_size":     ps,
        "page_count":    max(1, (int(total_count or 0) + ps - 1) // ps),
        "sort":          order_col,
        "direction":     order_dir.lower(),
        "search":        search or "",
        **_window_meta(w),
        "last_synced_at": _fmt(ls),
        "stale":          _is_stale(ls),
    }


def get_ar_invoices_list(
    conn, company_id: str,
    search: Any = None, bucket: Any = None, overdue_only: Any = False,
    page: int = 0, page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "outstanding_amount", direction: str = "desc",
) -> dict:
    """
    Detail O-list — paginated AR aging invoices.

    Filters: free-text `search` over customer_name / invoice_number, optional
    aging `bucket`, and `overdue_only`. AR is a snapshot, so there is no date
    window — but each row carries invoice_date / due_date for context.
    """
    p, ps = _clamp_page(page, page_size)
    where = ["company_id = %s"]
    params: list[Any] = [company_id]
    if search:
        where.append("(customer_name ILIKE %s OR invoice_number ILIKE %s)")
        like = f"%{search}%"
        params += [like, like]
    if bucket:
        where.append("aging_bucket = %s")
        params.append(bucket)
    if str(overdue_only).lower() in ("1", "true", "yes"):
        where.append("days_overdue > 0")
    where_sql = " AND ".join(where)

    sort_cols = {
        "outstanding_amount": "outstanding_amount", "days_overdue": "days_overdue",
        "invoice_date": "invoice_date", "due_date": "due_date",
        "customer_name": "customer_name", "invoice_amount": "invoice_amount",
    }
    order_col = sort_cols.get(sort, "outstanding_amount")
    order_dir = "ASC" if str(direction).lower() == "asc" else "DESC"

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*), COALESCE(SUM(outstanding_amount),0) "  # noqa: S608
            f"FROM tz_ar_aging WHERE {where_sql}",
            params,
        )
        total_count, filtered_total = cur.fetchone()

        cur.execute(
            f"""
            SELECT customer_name, invoice_number, invoice_date, due_date,
                   invoice_amount, outstanding_amount, days_overdue, aging_bucket
            FROM tz_ar_aging
            WHERE {where_sql}
            ORDER BY {order_col} {order_dir} NULLS LAST, customer_name
            LIMIT %s OFFSET %s
            """,  # noqa: S608
            params + [ps, p * ps],
        )
        rows = cur.fetchall()

    ls = _last_sync(conn, "ar_aging", company_id)
    return {
        "rows": [
            {
                "customer_name":      r[0],
                "invoice_number":     r[1],
                "invoice_date":       str(r[2]) if r[2] else None,
                "due_date":           str(r[3]) if r[3] else None,
                "invoice_amount":     float(r[4] or 0),
                "outstanding_amount": float(r[5] or 0),
                "days_overdue":       int(r[6] or 0),
                "aging_bucket":       r[7],
            }
            for r in rows
        ],
        "total_count":    int(total_count or 0),
        "filtered_total": float(filtered_total or 0),
        "page":           p,
        "page_size":      ps,
        "page_count":     max(1, (int(total_count or 0) + ps - 1) // ps),
        "sort":           order_col,
        "direction":      order_dir.lower(),
        "search":         search or "",
        "bucket":         bucket or "",
        "last_synced_at": _fmt(ls),
        "stale":          _is_stale(ls),
    }


# ────────────────────────────────────────────────────────────────────────────
# Generic paginated list builder — used by the transactional detail tables below.
# ────────────────────────────────────────────────────────────────────────────

def _paged_list(
    conn, company_id: str, *,
    table: str, pipeline: str,
    select_cols: list[str], row_map,
    search_cols: list[str], sum_col: str,
    sort_cols: dict, default_sort: str,
    date_col: str | None = None,
    start: Any = None, end: Any = None,
    search: Any = None,
    extra_where: list[str] | None = None, extra_params: list[Any] | None = None,
    page: int = 0, page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "", direction: str = "desc",
    extra_meta: dict | None = None,
) -> dict:
    """
    Build a paginated, searchable (and optionally date-windowed) detail list.

    `table`, `date_col`, `select_cols`, `search_cols`, `sum_col`, and the
    `sort_cols` values are all fixed identifiers from this module (never user
    input), so they are safe to interpolate. All user-supplied values go through
    parameter binding.
    """
    p, ps = _clamp_page(page, page_size)
    where = ["company_id = %s"]
    params: list[Any] = [company_id]
    window_meta: dict = {}

    if date_col:
        w = _resolve_window(conn, company_id, table, start, end, period_days=10**6)
        if not start and not end and w["data_from"]:
            w["start"] = w["data_from"]
        where += [f"{date_col} >= %s", f"{date_col} <= %s"]
        params += [w["start"].isoformat(), w["end"].isoformat()]
        window_meta = _window_meta(w)

    if search and search_cols:
        clause = " OR ".join(f"{c} ILIKE %s" for c in search_cols)
        where.append(f"({clause})")
        like = f"%{search}%"
        params += [like] * len(search_cols)

    if extra_where:
        where += extra_where
        params += extra_params or []

    where_sql = " AND ".join(where)
    order_col = sort_cols.get(sort, sort_cols.get(default_sort, default_sort))
    order_dir = "ASC" if str(direction).lower() == "asc" else "DESC"
    cols_sql = ", ".join(select_cols)

    with conn.cursor() as cur:
        cur.execute(
            f"SELECT COUNT(*), COALESCE(SUM({sum_col}),0) FROM {table} WHERE {where_sql}",  # noqa: S608
            params,
        )
        total_count, filtered_total = cur.fetchone()
        cur.execute(
            f"SELECT {cols_sql} FROM {table} WHERE {where_sql} "  # noqa: S608
            f"ORDER BY {order_col} {order_dir} NULLS LAST LIMIT %s OFFSET %s",
            params + [ps, p * ps],
        )
        rows = cur.fetchall()

    ls = _last_sync(conn, pipeline, company_id)
    return {
        "rows":           [row_map(r) for r in rows],
        "total_count":    int(total_count or 0),
        "filtered_total": float(filtered_total or 0),
        "page":           p,
        "page_size":      ps,
        "page_count":     max(1, (int(total_count or 0) + ps - 1) // ps),
        "sort":           order_col,
        "direction":      order_dir.lower(),
        "search":         search or "",
        **window_meta,
        **(extra_meta or {}),
        "last_synced_at": _fmt(ls),
        "stale":          _is_stale(ls),
    }


def get_purchase_invoices_list(
    conn, company_id: str,
    start: Any = None, end: Any = None, search: Any = None,
    page: int = 0, page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "invoice_date", direction: str = "desc",
) -> dict:
    """Paginated purchase-invoice lines (date-windowed + searchable)."""
    return _paged_list(
        conn, company_id, table="tz_purchase_invoices", pipeline="purchase_invoices",
        date_col="invoice_date", start=start, end=end, search=search,
        search_cols=["vendor_name", "invoice_number", "item_name", "item_code"],
        sum_col="line_total",
        select_cols=["invoice_date", "invoice_number", "vendor_name", "vendor_code",
                     "item_code", "item_name", "quantity", "unit_price", "line_total", "invoice_total"],
        row_map=lambda r: {
            "invoice_date":   str(r[0]) if r[0] else None,
            "invoice_number": r[1], "vendor_name": r[2], "vendor_code": r[3],
            "item_code": r[4], "item_name": r[5],
            "quantity": float(r[6] or 0), "unit_price": float(r[7] or 0),
            "line_total": float(r[8] or 0), "invoice_total": float(r[9] or 0),
        },
        sort_cols={"invoice_date": "invoice_date", "invoice_total": "invoice_total",
                   "line_total": "line_total", "vendor_name": "vendor_name", "quantity": "quantity"},
        default_sort="invoice_date", page=page, page_size=page_size, sort=sort, direction=direction,
    )


def get_sales_orders_list(
    conn, company_id: str,
    start: Any = None, end: Any = None, search: Any = None, status: Any = None,
    page: int = 0, page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "order_date", direction: str = "desc",
) -> dict:
    """Paginated sales-order lines (date-windowed, searchable, status filter)."""
    extra_where, extra_params = ([], [])
    if status:
        extra_where.append("status ILIKE %s")
        extra_params.append(status)
    return _paged_list(
        conn, company_id, table="tz_sales_orders", pipeline="sales_orders",
        date_col="order_date", start=start, end=end, search=search,
        search_cols=["customer_name", "order_number", "sku_name", "sku_code"],
        sum_col="order_value",
        select_cols=["order_date", "order_number", "customer_name", "sku_code", "sku_name",
                     "ordered_qty", "dispatched_qty", "pending_qty", "order_value", "delivery_date", "status"],
        row_map=lambda r: {
            "order_date": str(r[0]) if r[0] else None, "order_number": r[1],
            "customer_name": r[2], "sku_code": r[3], "sku_name": r[4],
            "ordered_qty": float(r[5] or 0), "dispatched_qty": float(r[6] or 0),
            "pending_qty": float(r[7] or 0), "order_value": float(r[8] or 0),
            "delivery_date": str(r[9]) if r[9] else None, "status": r[10],
        },
        sort_cols={"order_date": "order_date", "order_value": "order_value",
                   "customer_name": "customer_name", "pending_qty": "pending_qty",
                   "delivery_date": "delivery_date"},
        default_sort="order_date", extra_where=extra_where, extra_params=extra_params,
        page=page, page_size=page_size, sort=sort, direction=direction,
        extra_meta={"status": status or ""},
    )


def get_purchase_orders_list(
    conn, company_id: str,
    start: Any = None, end: Any = None, search: Any = None, status: Any = None,
    page: int = 0, page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "po_date", direction: str = "desc",
) -> dict:
    """Paginated purchase-order lines (date-windowed, searchable, status filter)."""
    extra_where, extra_params = ([], [])
    if status:
        extra_where.append("status ILIKE %s")
        extra_params.append(status)
    return _paged_list(
        conn, company_id, table="tz_purchase_orders", pipeline="purchase_orders",
        date_col="po_date", start=start, end=end, search=search,
        search_cols=["vendor_name", "po_number", "item_name", "item_code"],
        sum_col="po_value",
        select_cols=["po_date", "po_number", "vendor_name", "item_code", "item_name",
                     "ordered_qty", "received_qty", "pending_qty", "po_value", "expected_date", "status"],
        row_map=lambda r: {
            "po_date": str(r[0]) if r[0] else None, "po_number": r[1],
            "vendor_name": r[2], "item_code": r[3], "item_name": r[4],
            "ordered_qty": float(r[5] or 0), "received_qty": float(r[6] or 0),
            "pending_qty": float(r[7] or 0), "po_value": float(r[8] or 0),
            "expected_date": str(r[9]) if r[9] else None, "status": r[10],
        },
        sort_cols={"po_date": "po_date", "po_value": "po_value",
                   "vendor_name": "vendor_name", "pending_qty": "pending_qty",
                   "expected_date": "expected_date"},
        default_sort="po_date", extra_where=extra_where, extra_params=extra_params,
        page=page, page_size=page_size, sort=sort, direction=direction,
        extra_meta={"status": status or ""},
    )


def get_production_list(
    conn, company_id: str,
    start: Any = None, end: Any = None, search: Any = None, status: Any = None,
    page: int = 0, page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "production_date", direction: str = "desc",
) -> dict:
    """Paginated production process records (date-windowed, searchable, status filter)."""
    extra_where, extra_params = ([], [])
    if status:
        extra_where.append("status ILIKE %s")
        extra_params.append(status)
    return _paged_list(
        conn, company_id, table="tz_process_details", pipeline="process_details",
        date_col="production_date", start=start, end=end, search=search,
        search_cols=["work_order_number", "sku_name", "sku_code", "process_name"],
        sum_col="produced_qty",
        select_cols=["production_date", "work_order_number", "sku_code", "sku_name",
                     "process_name", "planned_qty", "produced_qty", "rejected_qty", "status"],
        row_map=lambda r: {
            "production_date": str(r[0]) if r[0] else None, "work_order_number": r[1],
            "sku_code": r[2], "sku_name": r[3], "process_name": r[4],
            "planned_qty": float(r[5] or 0), "produced_qty": float(r[6] or 0),
            "rejected_qty": float(r[7] or 0), "status": r[8],
        },
        sort_cols={"production_date": "production_date", "produced_qty": "produced_qty",
                   "rejected_qty": "rejected_qty", "planned_qty": "planned_qty",
                   "work_order_number": "work_order_number"},
        default_sort="production_date", extra_where=extra_where, extra_params=extra_params,
        page=page, page_size=page_size, sort=sort, direction=direction,
        extra_meta={"status": status or ""},
    )


def get_inventory_list(
    conn, company_id: str,
    search: Any = None, category: Any = None,
    page: int = 0, page_size: int = DEFAULT_PAGE_SIZE,
    sort: str = "total_value", direction: str = "desc",
) -> dict:
    """Paginated inventory valuation rows (snapshot — no date window, category filter)."""
    extra_where, extra_params = ([], [])
    if category:
        extra_where.append("category = %s")
        extra_params.append(category)
    return _paged_list(
        conn, company_id, table="tz_inventory_valuation", pipeline="inventory_valuation",
        date_col=None, search=search,
        search_cols=["sku_code", "sku_name", "category", "warehouse"],
        sum_col="total_value",
        select_cols=["sku_code", "sku_name", "category", "warehouse", "quantity",
                     "unit_cost", "total_value", "is_raw_material", "is_negative_stock"],
        row_map=lambda r: {
            "sku_code": r[0], "sku_name": r[1], "category": r[2], "warehouse": r[3],
            "quantity": float(r[4] or 0), "unit_cost": float(r[5] or 0),
            "total_value": float(r[6] or 0),
            "is_raw_material": bool(r[7]), "is_negative_stock": bool(r[8]),
        },
        sort_cols={"total_value": "total_value", "quantity": "quantity",
                   "unit_cost": "unit_cost", "sku_name": "sku_name", "category": "category"},
        default_sort="total_value", extra_where=extra_where, extra_params=extra_params,
        page=page, page_size=page_size, sort=sort, direction=direction,
        extra_meta={"category": category or ""},
    )


# ════════════════════════════════════════════════════════════════════════════
# UTILITY
# ════════════════════════════════════════════════════════════════════════════

def get_sync_health(conn, company_id: str) -> dict:
    """
    /dashboard/sync/health — freshness of all 10 pipelines for this brand.
    Always reads live from tz_sync_runs (no caching).
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT ON (pipeline_name)
                pipeline_name,
                status,
                completed_at,
                rows_fetched,
                rows_upserted,
                error_message
            FROM tz_sync_runs
            WHERE company_id = %s
            ORDER BY pipeline_name, completed_at DESC NULLS LAST
        """, (company_id,))
        rows = cur.fetchall()

    pipelines = []
    for r in rows:
        last_sync_ts = r[2]
        stale = _is_stale(last_sync_ts)
        pipelines.append({
            "pipeline_name":  r[0],
            "status":         r[1],
            "completed_at":   _fmt(last_sync_ts),
            "rows_fetched":   r[3],
            "rows_upserted":  r[4],
            "error_message":  r[5],
            "stale":          stale,
        })

    all_healthy = all(p["status"] == "success" and not p["stale"] for p in pipelines)
    return {
        "all_healthy":  all_healthy,
        "pipeline_count": len(pipelines),
        "pipelines":    pipelines,
        "checked_at":   _fmt(_now_utc()),
    }
