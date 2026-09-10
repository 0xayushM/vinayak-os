"""
schema/pulse.py
────────────────
The Pulse — the cards the owner sees first each morning, and the payload the
daily brief is written from.

A card earns its place only if it names a DELTA, a CAUSE, or a DECISION:
a number on its own belongs one click down, on the Explore pages. Every card
therefore carries the same five things:

    headline    the figure
    change      how it compares to this business's OWN normal (never a
                calendar period picked for us)
    why         one sentence of attribution — who or what moved it
    action      what can be started from here (or None)
    trust       freshness + a confidence label computed the same way the
                reasoning engine computes it (CERTAIN / PROBABLE / UNCERTAIN)

Formulas are the ones specified in docs/V0_FINANCE_SPEC.md §2, implemented
over data we already sync. Two of them (payment behaviour, DSO trend) run on
a proxy until enough AR history has accumulated; those cards say so and
report PROBABLE rather than pretending.

Conventions match schema/queries.py: company-scoped, typed dicts out, never
raw rows, Top-N capped.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from vinayak.domain.money import Money
from vinayak.schema.queries import _date_range, _fmt, _is_stale, _last_sync

logger = logging.getLogger(__name__)

CERTAIN, PROBABLE, UNCERTAIN = "CERTAIN", "PROBABLE", "UNCERTAIN"

# How much of the overdue book we assume actually lands inside 30 days.
# v1 constant; recalibrated from inferred payments once history allows.
OVERDUE_COLLECTION_FACTOR = 0.5
# A customer is "regular" if it has this many gaps and a median gap this short.
REORDER_MIN_ORDERS = 4
REORDER_MAX_MEDIAN_GAP = 60
REORDER_FLAG_MULTIPLE = 1.5
# Top-N cap on the inferred-payment list handed to a model or a screen.
MAX_INVOICES_PULSE = 25


def _pct(part: float, whole: float) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def _inr(v: float | None) -> str:
    return Money.compact(v)


# ══════════════════════════════════════════════════════════════════════════
# History helpers — the AR snapshot is the only memory of yesterday we have
# ══════════════════════════════════════════════════════════════════════════

def snapshot_dates(conn, company_id: str, limit: int = 200) -> list[date]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT DISTINCT snap_date FROM ar_daily_snapshot WHERE company_id = %s "
            "ORDER BY snap_date DESC LIMIT %s", (company_id, limit))
        return [r[0] for r in cur.fetchall()]


def _nearest_snapshot(dates: list[date], target: date) -> date | None:
    """The snapshot on or before `target` (snapshots can miss a day)."""
    older = [d for d in dates if d <= target]
    return max(older) if older else None


def get_inferred_payments(conn, company_id: str, window_days: int = 180) -> dict:
    """Payments inferred from the AR book's own history: an invoice present on
    day D with a balance and gone on the next snapshot was paid in between.
    This is the only way we learn actual payment DATES — TranzAct's AR report
    is a snapshot with no receipt data.

    Returns: payments (capped), count, avg_days_to_pay, median_days_to_pay,
             history_days (how much snapshot history exists).
    """
    dates = snapshot_dates(conn, company_id)
    history_days = (max(dates) - min(dates)).days if len(dates) >= 2 else 0
    if len(dates) < 2:
        return {"payments": [], "count": 0, "avg_days_to_pay": None,
                "median_days_to_pay": None, "history_days": history_days,
                "history_building": True}
    since = (max(dates) - timedelta(days=window_days))
    with conn.cursor() as cur:
        cur.execute("""
            WITH snaps AS (
                SELECT DISTINCT snap_date FROM ar_daily_snapshot
                WHERE company_id = %s AND snap_date >= %s
            ),
            pairs AS (
                SELECT snap_date AS d, LEAD(snap_date) OVER (ORDER BY snap_date) AS nd
                FROM snaps
            ),
            paid AS (
                SELECT s.invoice_ref, s.customer_name, s.invoice_number,
                       s.invoice_date, s.due_date, s.outstanding, p.nd AS paid_on
                FROM ar_daily_snapshot s
                JOIN pairs p ON p.d = s.snap_date
                WHERE s.company_id = %s AND s.snap_date >= %s
                  AND COALESCE(s.outstanding, 0) > 0 AND p.nd IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1 FROM ar_daily_snapshot s2
                      WHERE s2.company_id = s.company_id AND s2.snap_date = p.nd
                        AND s2.invoice_ref = s.invoice_ref
                        AND COALESCE(s2.outstanding, 0) > 0)
            )
            SELECT customer_name, invoice_number, invoice_date, due_date, outstanding,
                   paid_on, (paid_on - invoice_date) AS days_to_pay,
                   (paid_on - due_date) AS days_late
            FROM paid
            WHERE invoice_date IS NOT NULL
            ORDER BY paid_on DESC
            LIMIT 500
        """, (company_id, since, company_id, since))
        rows = cur.fetchall()

    payments = [{"customer_name": r[0], "invoice_number": r[1],
                 "invoice_date": r[2].isoformat() if r[2] else None,
                 "due_date": r[3].isoformat() if r[3] else None,
                 "amount": float(r[4] or 0), "paid_on": r[5].isoformat() if r[5] else None,
                 "days_to_pay": int(r[6]) if r[6] is not None else None,
                 "days_late": int(r[7]) if r[7] is not None else None} for r in rows]
    dtp = sorted(p["days_to_pay"] for p in payments if p["days_to_pay"] is not None)
    avg = round(sum(dtp) / len(dtp), 1) if dtp else None
    med = dtp[len(dtp) // 2] if dtp else None
    return {"payments": payments[:MAX_INVOICES_PULSE], "count": len(payments),
            "avg_days_to_pay": avg, "median_days_to_pay": med,
            "history_days": history_days, "history_building": history_days < 14}


# ══════════════════════════════════════════════════════════════════════════
# P1 · Aging drift — "is money sliding toward bad?"
# ══════════════════════════════════════════════════════════════════════════

def _bucket_totals(conn, company_id: str, snap: date) -> dict[str, float]:
    """Bucket totals as of one snapshot, aged from the invoice date the same
    way get_ar_summary ages the live book — so drift is comparable."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT CASE
                     WHEN (%s - invoice_date) <= 30 THEN '0-30'
                     WHEN (%s - invoice_date) <= 60 THEN '31-60'
                     WHEN (%s - invoice_date) <= 90 THEN '61-90'
                     ELSE '90+' END AS bucket,
                   COALESCE(SUM(outstanding), 0)
            FROM ar_daily_snapshot
            WHERE company_id = %s AND snap_date = %s
              AND COALESCE(outstanding, 0) > 0 AND invoice_date IS NOT NULL
            GROUP BY 1
        """, (snap, snap, snap, company_id, snap))
        return {r[0]: float(r[1] or 0) for r in cur.fetchall()}


def get_aging_drift(conn, company_id: str, window_days: int = 30) -> dict:
    """Value that moved INTO the two worst buckets over the window, plus the
    customers who account for it. Needs at least two snapshots."""
    dates = snapshot_dates(conn, company_id)
    ls = _last_sync(conn, "ar_aging", company_id)
    base = {"window_days": window_days, "last_synced_at": _fmt(ls), "stale": _is_stale(ls)}
    if not dates:
        return {**base, "history_building": True, "history_days": 0,
                "buckets_now": {}, "drift": 0.0, "drift_pct": 0.0, "movers": []}
    now_d = max(dates)
    then_d = _nearest_snapshot(dates, now_d - timedelta(days=window_days))
    now = _bucket_totals(conn, company_id, now_d)
    total_now = sum(now.values())
    if then_d is None or then_d == now_d:
        return {**base, "history_building": True,
                "history_days": (now_d - min(dates)).days,
                "buckets_now": now, "total_outstanding": total_now,
                "drift": 0.0, "drift_pct": 0.0, "movers": []}

    then = _bucket_totals(conn, company_id, then_d)
    bad_now = now.get("61-90", 0) + now.get("90+", 0)
    bad_then = then.get("61-90", 0) + then.get("90+", 0)
    drift = bad_now - bad_then

    # Who moved: customers whose 61+ exposure grew most over the window.
    with conn.cursor() as cur:
        cur.execute("""
            WITH now_bad AS (
                SELECT customer_name, COALESCE(SUM(outstanding),0) AS v
                FROM ar_daily_snapshot
                WHERE company_id=%s AND snap_date=%s AND (%s - invoice_date) > 60
                  AND COALESCE(outstanding,0) > 0
                GROUP BY customer_name),
            then_bad AS (
                SELECT customer_name, COALESCE(SUM(outstanding),0) AS v
                FROM ar_daily_snapshot
                WHERE company_id=%s AND snap_date=%s AND (%s - invoice_date) > 60
                  AND COALESCE(outstanding,0) > 0
                GROUP BY customer_name)
            SELECT COALESCE(n.customer_name, t.customer_name),
                   COALESCE(n.v,0) - COALESCE(t.v,0) AS delta, COALESCE(n.v,0)
            FROM now_bad n FULL OUTER JOIN then_bad t USING (customer_name)
            ORDER BY delta DESC LIMIT 5
        """, (company_id, now_d, now_d, company_id, then_d, then_d))
        movers = [{"customer_name": r[0], "delta": float(r[1] or 0), "now": float(r[2] or 0)}
                  for r in cur.fetchall() if float(r[1] or 0) > 0]

    return {**base, "history_building": False,
            "history_days": (now_d - min(dates)).days,
            "as_of": now_d.isoformat(), "compared_to": then_d.isoformat(),
            "buckets_now": now, "buckets_then": then,
            "total_outstanding": total_now,
            "bad_now": bad_now, "bad_then": bad_then,
            "drift": drift, "drift_pct": _pct(drift, total_now), "movers": movers}


# ══════════════════════════════════════════════════════════════════════════
# P2 · Payment behaviour — "who is getting slower?"
# ══════════════════════════════════════════════════════════════════════════

def _norm_days(d: float | None, cap: int = 120) -> float:
    return min(max(float(d or 0), 0.0), cap) / cap


def get_payment_behaviour(conn, company_id: str, top_n: int = 8) -> dict:
    """v1 (day one): a composite risk score from the CURRENT book —
    overdue share, oldest overdue, weighted average lateness.
    v2 (with ≥ 60 days of snapshots): the change in average days-to-pay,
    this 90 days vs the 90 before. v2 is reported when available; the card
    labels which one it is showing."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT customer_name,
                   COALESCE(SUM(outstanding_amount),0)                                   AS outstanding,
                   COALESCE(SUM(outstanding_amount) FILTER (WHERE (CURRENT_DATE - due_date) > 0),0) AS overdue,
                   MAX(CURRENT_DATE - due_date)                                          AS oldest,
                   COALESCE(SUM(outstanding_amount * GREATEST(CURRENT_DATE - due_date,0))
                            / NULLIF(SUM(outstanding_amount),0), 0)                      AS wtd_late
            FROM canon_ar_flat
            WHERE company_id = %s AND COALESCE(outstanding_amount,0) > 0
            GROUP BY customer_name
        """, (company_id,))
        rows = cur.fetchall()

    items = []
    for name, outstanding, overdue, oldest, wtd in rows:
        outstanding, overdue = float(outstanding or 0), float(overdue or 0)
        score = (0.4 * (overdue / outstanding if outstanding else 0)
                 + 0.3 * _norm_days(oldest)
                 + 0.3 * _norm_days(wtd))
        items.append({"customer_name": name, "outstanding": outstanding, "overdue": overdue,
                      "oldest_days_overdue": int(oldest or 0),
                      "weighted_days_late": round(float(wtd or 0), 1),
                      "score": round(score, 3)})
    items.sort(key=lambda x: x["score"], reverse=True)

    # v2: has the average days-to-pay worsened?
    inferred = get_inferred_payments(conn, company_id, window_days=180)
    worsened: list[dict] = []
    basis = "current_book"
    if not inferred["history_building"] and inferred["count"] >= 10:
        by_cust: dict[str, list[tuple[str, int]]] = {}
        for p in inferred["payments"]:
            if p["days_to_pay"] is None or not p["paid_on"]:
                continue
            by_cust.setdefault(p["customer_name"], []).append((p["paid_on"], p["days_to_pay"]))
        cutoff = (date.today() - timedelta(days=90)).isoformat()
        for name, ps in by_cust.items():
            recent = [d for on, d in ps if on >= cutoff]
            prior = [d for on, d in ps if on < cutoff]
            if len(recent) >= 2 and len(prior) >= 2:
                delta = sum(recent) / len(recent) - sum(prior) / len(prior)
                if delta > 10:
                    worsened.append({"customer_name": name, "days_slower": round(delta, 1),
                                     "avg_now": round(sum(recent) / len(recent), 1),
                                     "avg_before": round(sum(prior) / len(prior), 1)})
        worsened.sort(key=lambda x: x["days_slower"], reverse=True)
        if worsened:
            basis = "days_to_pay"

    ls = _last_sync(conn, "ar_aging", company_id)
    return {"items": items[:top_n], "worsened": worsened[:top_n], "basis": basis,
            "payment_history_days": inferred["history_days"],
            "avg_days_to_pay": inferred["avg_days_to_pay"],
            "last_synced_at": _fmt(ls), "stale": _is_stale(ls)}


# ══════════════════════════════════════════════════════════════════════════
# P3 · 30-day cash view — "what's coming in vs going out?"
# ══════════════════════════════════════════════════════════════════════════

def get_cash_30d(conn, company_id: str, horizon_days: int = 30) -> dict:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(outstanding_amount) FILTER (
                       WHERE due_date BETWEEN CURRENT_DATE AND CURRENT_DATE + %s), 0),
                   COALESCE(SUM(outstanding_amount) FILTER (
                       WHERE due_date < CURRENT_DATE), 0)
            FROM canon_ar_flat
            WHERE company_id = %s AND COALESCE(outstanding_amount,0) > 0
        """, (horizon_days, company_id))
        due_soon, overdue = (float(x or 0) for x in cur.fetchone())
        cur.execute("""
            SELECT COALESCE(SUM(po_value), 0), COUNT(DISTINCT po_number)
            FROM canon_purchase_order_flat
            WHERE company_id = %s AND COALESCE(pending_qty, 0) > 0
              AND expected_date IS NOT NULL AND expected_date <= CURRENT_DATE + %s
        """, (company_id, horizon_days))
        po_row = cur.fetchone()
        outflow, po_count = float(po_row[0] or 0), int(po_row[1] or 0)

    expected_from_overdue = overdue * OVERDUE_COLLECTION_FACTOR
    inflow = due_soon + expected_from_overdue
    net = inflow - outflow
    ls = _last_sync(conn, "ar_aging", company_id)
    return {"horizon_days": horizon_days,
            "inflow_due": due_soon, "overdue_total": overdue,
            "inflow_expected_from_overdue": expected_from_overdue,
            "collection_factor": OVERDUE_COLLECTION_FACTOR,
            "inflow": inflow, "outflow": outflow, "open_po_count": po_count,
            "net": net, "last_synced_at": _fmt(ls), "stale": _is_stale(ls)}


# ══════════════════════════════════════════════════════════════════════════
# P4 · What changed this week — "why is revenue up or down?"
# ══════════════════════════════════════════════════════════════════════════

def get_week_delta(conn, company_id: str, weeks_baseline: int = 8) -> dict:
    """Last 7 data-days against the trailing weekly mean, with the customers
    and SKUs that account for the difference. Anchored to the latest invoice
    date, never to today — so a Friday sync doesn't show an empty week."""
    _f, data_to = _date_range(conn, company_id, "canon_sales_invoice_flat")
    ls = _last_sync(conn, "sales_invoices", company_id)
    base = {"last_synced_at": _fmt(ls), "stale": _is_stale(ls)}
    if not data_to:
        return {**base, "this_week": 0.0, "usual_week": 0.0, "delta": 0.0,
                "delta_pct": 0.0, "contributors": [], "skus": [], "no_data": True}

    wk_from = data_to - timedelta(days=6)
    base_from = data_to - timedelta(days=6 + 7 * weeks_baseline)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COALESCE(SUM(line_total), 0)
            FROM canon_sales_invoice_flat
            WHERE company_id=%s AND invoice_date BETWEEN %s AND %s
        """, (company_id, wk_from, data_to))
        this_week = float(cur.fetchone()[0] or 0)
        cur.execute("""
            SELECT COALESCE(SUM(line_total), 0)
            FROM canon_sales_invoice_flat
            WHERE company_id=%s AND invoice_date >= %s AND invoice_date < %s
        """, (company_id, base_from, wk_from))
        baseline_total = float(cur.fetchone()[0] or 0)
        usual = baseline_total / weeks_baseline if weeks_baseline else 0.0

        cur.execute("""
            WITH this AS (
                SELECT customer_name, COALESCE(SUM(line_total),0) AS v
                FROM canon_sales_invoice_flat
                WHERE company_id=%s AND invoice_date BETWEEN %s AND %s
                GROUP BY customer_name),
            prior AS (
                SELECT customer_name, COALESCE(SUM(line_total),0)/%s AS v
                FROM canon_sales_invoice_flat
                WHERE company_id=%s AND invoice_date >= %s AND invoice_date < %s
                GROUP BY customer_name)
            SELECT COALESCE(t.customer_name, p.customer_name),
                   COALESCE(t.v,0) - COALESCE(p.v,0) AS contribution,
                   COALESCE(t.v,0), COALESCE(p.v,0)
            FROM this t FULL OUTER JOIN prior p USING (customer_name)
            ORDER BY ABS(COALESCE(t.v,0) - COALESCE(p.v,0)) DESC
            LIMIT 5
        """, (company_id, wk_from, data_to, weeks_baseline, company_id, base_from, wk_from))
        contributors = [{"customer_name": r[0], "contribution": float(r[1] or 0),
                         "this_week": float(r[2] or 0), "usual": float(r[3] or 0)}
                        for r in cur.fetchall()]

        cur.execute("""
            WITH this AS (
                SELECT sku_code, MAX(sku_name) AS sku_name, COALESCE(SUM(line_total),0) AS v
                FROM canon_sales_invoice_flat
                WHERE company_id=%s AND invoice_date BETWEEN %s AND %s
                GROUP BY sku_code),
            prior AS (
                SELECT sku_code, COALESCE(SUM(line_total),0)/%s AS v
                FROM canon_sales_invoice_flat
                WHERE company_id=%s AND invoice_date >= %s AND invoice_date < %s
                GROUP BY sku_code)
            SELECT COALESCE(t.sku_code, p.sku_code), t.sku_name,
                   COALESCE(t.v,0) - COALESCE(p.v,0) AS contribution
            FROM this t FULL OUTER JOIN prior p USING (sku_code)
            ORDER BY ABS(COALESCE(t.v,0) - COALESCE(p.v,0)) DESC
            LIMIT 5
        """, (company_id, wk_from, data_to, weeks_baseline, company_id, base_from, wk_from))
        skus = [{"sku_code": r[0], "sku_name": r[1], "contribution": float(r[2] or 0)}
                for r in cur.fetchall()]

    delta = this_week - usual
    return {**base, "week_from": wk_from.isoformat(), "week_to": data_to.isoformat(),
            "this_week": this_week, "usual_week": usual, "weeks_baseline": weeks_baseline,
            "delta": delta, "delta_pct": _pct(delta, usual) if usual else 0.0,
            "contributors": contributors, "skus": skus, "no_data": False}


# ══════════════════════════════════════════════════════════════════════════
# P5 · Reorder radar — "which regulars are overdue to order?"
# ══════════════════════════════════════════════════════════════════════════

def get_reorder_status(conn, company_id: str, top_n: int = 10) -> dict:
    """Customers with a settled buying rhythm who are past 1.5× their own
    median gap. Their own history is the benchmark — never a fixed number of
    days, which would flag every seasonal buyer."""
    _f, data_to = _date_range(conn, company_id, "canon_sales_invoice_flat")
    anchor = data_to or date.today()
    since = anchor - timedelta(days=365)
    with conn.cursor() as cur:
        cur.execute("""
            WITH orders AS (
                SELECT DISTINCT customer_name, invoice_date
                FROM canon_sales_invoice_flat
                WHERE company_id = %s AND invoice_date >= %s AND customer_name IS NOT NULL
            ),
            gaps AS (
                SELECT customer_name,
                       invoice_date - LAG(invoice_date) OVER (PARTITION BY customer_name ORDER BY invoice_date) AS gap
                FROM orders
            ),
            stats AS (
                SELECT customer_name,
                       COUNT(*) FILTER (WHERE gap IS NOT NULL)                          AS gap_count,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY gap)                 AS median_gap
                FROM gaps GROUP BY customer_name
            ),
            last_order AS (
                SELECT customer_name, MAX(invoice_date) AS last_date,
                       COUNT(DISTINCT invoice_date) AS order_count
                FROM orders GROUP BY customer_name
            ),
            value AS (
                SELECT customer_name,
                       COALESCE(SUM(line_total),0) / NULLIF(COUNT(DISTINCT invoice_number),0) AS avg_order_value
                FROM canon_sales_invoice_flat
                WHERE company_id = %s AND invoice_date >= %s
                GROUP BY customer_name
            )
            SELECT s.customer_name, s.median_gap, l.last_date, l.order_count,
                   (%s - l.last_date) AS days_since, v.avg_order_value
            FROM stats s
            JOIN last_order l USING (customer_name)
            LEFT JOIN value v USING (customer_name)
            WHERE s.gap_count >= 3 AND s.median_gap IS NOT NULL
              AND s.median_gap <= %s AND l.order_count >= %s
              AND (%s - l.last_date) > s.median_gap * %s
            ORDER BY v.avg_order_value DESC NULLS LAST
            LIMIT %s
        """, (company_id, since, company_id, since, anchor,
              REORDER_MAX_MEDIAN_GAP, REORDER_MIN_ORDERS, anchor,
              REORDER_FLAG_MULTIPLE, top_n))
        rows = cur.fetchall()
    items = [{"customer_name": r[0], "median_gap_days": int(round(float(r[1] or 0))),
              "last_order": r[2].isoformat() if r[2] else None, "order_count": int(r[3] or 0),
              "days_since_last": int(r[4] or 0), "avg_order_value": float(r[5] or 0)}
             for r in rows]
    ls = _last_sync(conn, "sales_invoices", company_id)
    return {"items": items, "flagged_count": len(items),
            "value_at_stake": round(sum(i["avg_order_value"] for i in items), 2),
            "anchor_date": anchor.isoformat(),
            "last_synced_at": _fmt(ls), "stale": _is_stale(ls)}


# ══════════════════════════════════════════════════════════════════════════
# P6 · Concentration trend — "is dependence growing?"
# ══════════════════════════════════════════════════════════════════════════

def get_concentration_trend(conn, company_id: str, window_days: int = 90) -> dict:
    _f, data_to = _date_range(conn, company_id, "canon_sales_invoice_flat")
    anchor = data_to or date.today()
    now_from = anchor - timedelta(days=window_days)
    prev_from = anchor - timedelta(days=window_days * 2)

    def shares(from_d: date, to_d: date) -> tuple[float, float, str | None, float]:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT customer_name, COALESCE(SUM(line_total),0) AS v
                FROM canon_sales_invoice_flat
                WHERE company_id=%s AND invoice_date >= %s AND invoice_date < %s
                GROUP BY customer_name ORDER BY v DESC
            """, (company_id, from_d, to_d))
            rows = [(r[0], float(r[1] or 0)) for r in cur.fetchall()]
        total = sum(v for _, v in rows)
        top1 = rows[0][1] if rows else 0.0
        top3 = sum(v for _, v in rows[:3])
        return (_pct(top1, total), _pct(top3, total), rows[0][0] if rows else None, total)

    t1_now, t3_now, top_name, total_now = shares(now_from, anchor + timedelta(days=1))
    t1_prev, t3_prev, _n, total_prev = shares(prev_from, now_from)
    ls = _last_sync(conn, "sales_invoices", company_id)
    return {"window_days": window_days, "top1_pct": t1_now, "top3_pct": t3_now,
            "top1_pct_prev": t1_prev, "top3_pct_prev": t3_prev,
            "top1_change": round(t1_now - t1_prev, 1), "top3_change": round(t3_now - t3_prev, 1),
            "top_customer": top_name, "revenue_window": total_now, "revenue_prev": total_prev,
            "last_synced_at": _fmt(ls), "stale": _is_stale(ls)}


# ══════════════════════════════════════════════════════════════════════════
# P7 · Trapped capital — "is dead stock growing?"
# ══════════════════════════════════════════════════════════════════════════

def get_dead_stock_delta(conn, company_id: str, since_days: int = 90,
                         compare_days: int = 30) -> dict:
    """Dead-stock value now vs the same rule applied `compare_days` ago.
    Stock quantities are a live snapshot, so the comparison moves the SALES
    window, not the stock — it answers "would this have counted as dead a
    month ago?", which is the question the owner is actually asking."""
    _f, data_to = _date_range(conn, company_id, "canon_sales_invoice_flat")
    anchor = data_to or date.today()

    def dead_value(as_of: date) -> tuple[float, int]:
        cutoff = as_of - timedelta(days=since_days)
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(SUM(i.total_value),0), COUNT(*)
                FROM canon_inventory_flat i
                WHERE i.company_id = %s AND COALESCE(i.quantity,0) > 0
                  AND NOT EXISTS (
                      SELECT 1 FROM canon_sales_invoice_flat s
                      WHERE s.company_id = i.company_id AND s.sku_code = i.sku_code
                        AND s.invoice_date >= %s AND s.invoice_date <= %s)
            """, (company_id, cutoff, as_of))
            r = cur.fetchone()
        return float(r[0] or 0), int(r[1] or 0)

    now_v, now_n = dead_value(anchor)
    then_v, then_n = dead_value(anchor - timedelta(days=compare_days))
    ls = _last_sync(conn, "inventory_valuation", company_id)
    return {"dead_value": now_v, "dead_count": now_n,
            "dead_value_before": then_v, "dead_count_before": then_n,
            "delta": now_v - then_v, "delta_pct": _pct(now_v - then_v, then_v) if then_v else 0.0,
            "since_days": since_days, "compare_days": compare_days,
            "last_synced_at": _fmt(ls), "stale": _is_stale(ls)}


# ══════════════════════════════════════════════════════════════════════════
# P8 · Anomalies — "things that shouldn't happen"
# ══════════════════════════════════════════════════════════════════════════

def get_anomalies(conn, company_id: str, cap: int = 6) -> dict:
    """A union of deterministic rule flags, capped and one sentence each.
    Every one is a fact from the data, never a model's opinion."""
    out: list[dict] = []
    with conn.cursor() as cur:
        # negative or impossible stock — a data-integrity problem, not a business one
        cur.execute("""
            SELECT COUNT(*), COALESCE(SUM(total_value),0)
            FROM canon_inventory_flat
            WHERE company_id=%s AND COALESCE(quantity,0) < 0
        """, (company_id,))
        n, v = cur.fetchone()
        if int(n or 0):
            out.append({"kind": "negative_stock", "severity": 60,
                        "text": (f"{int(n)} SKU{'s' if int(n) > 1 else ''} "
                                 f"show{'' if int(n) > 1 else 's'} negative stock — a data-entry or "
                                 f"sequence error, not real stock."),
                        "count": int(n), "value": float(v or 0)})

        # an invoice far above that customer's own normal
        cur.execute("""
            WITH inv AS (
                SELECT customer_name, invoice_number, invoice_date,
                       SUM(line_total) AS v
                FROM canon_sales_invoice_flat
                WHERE company_id=%s AND invoice_date >= CURRENT_DATE - 30
                GROUP BY customer_name, invoice_number, invoice_date),
            med AS (
                SELECT customer_name,
                       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY v) AS m,
                       COUNT(*) AS n
                FROM (SELECT customer_name, invoice_number, SUM(line_total) AS v
                      FROM canon_sales_invoice_flat
                      WHERE company_id=%s GROUP BY customer_name, invoice_number) x
                GROUP BY customer_name)
            SELECT i.customer_name, i.invoice_number, i.v, m.m
            FROM inv i JOIN med m USING (customer_name)
            WHERE m.n >= 5 AND m.m > 0 AND i.v > 4 * m.m
            ORDER BY i.v DESC LIMIT 3
        """, (company_id, company_id))
        for cust, num, v, m in cur.fetchall():
            out.append({"kind": "outsized_invoice", "severity": 40,
                        "text": f"Invoice {num} to {cust} is {_inr(float(v))} — about {round(float(v)/float(m))}× their usual {_inr(float(m))}.",
                        "entity_ref": f"customer:{cust}", "value": float(v)})

        # a vendor charging materially more than last time for the same item
        cur.execute("""
            WITH prices AS (
                SELECT vendor_name, item_code, item_name, po_date,
                       po_value / NULLIF(ordered_qty,0) AS unit_price,
                       ROW_NUMBER() OVER (PARTITION BY vendor_name, item_code ORDER BY po_date DESC) AS rn
                FROM canon_purchase_order_flat
                WHERE company_id=%s AND COALESCE(ordered_qty,0) > 0 AND COALESCE(po_value,0) > 0
            )
            SELECT a.vendor_name, a.item_code, a.item_name, a.unit_price, b.unit_price, a.po_date
            FROM prices a JOIN prices b
              ON a.vendor_name=b.vendor_name AND a.item_code=b.item_code AND a.rn=1 AND b.rn=2
            WHERE a.unit_price > b.unit_price * 1.25 AND a.po_date >= CURRENT_DATE - 60
            ORDER BY (a.unit_price - b.unit_price) DESC LIMIT 3
        """, (company_id,))
        for vendor, item_code, item, new_p, old_p, po_d in cur.fetchall():
            pct = round((float(new_p) / float(old_p) - 1) * 100)
            out.append({"kind": "vendor_price_jump", "severity": 45,
                        "text": f"{vendor} raised {item} by {pct}% — {_inr(float(old_p))} to {_inr(float(new_p))} per unit.",
                        "entity_ref": f"vendor:{vendor}", "value": float(new_p),
                        # carried so an experiment on this rise has something to measure
                        "vendor_name": vendor, "item_code": item_code, "item_name": item,
                        "previous_unit_price": float(old_p)})

    # stale feeds — the trust flag every card already shows, summarised once
    from vinayak.schema.queries import get_sync_health
    try:
        health = get_sync_health(conn, company_id)
        stale = [p["pipeline_name"] for p in health.get("pipelines", []) if p.get("stale")]
        if stale:
            out.append({"kind": "data_stale", "severity": 70,
                        "text": f"{len(stale)} feed{'s' if len(stale) > 1 else ''} last synced over 25 hours ago: {', '.join(stale[:4])}.",
                        "count": len(stale)})
    except Exception as exc:  # noqa: BLE001
        logger.warning("anomalies: sync health failed: %s", exc)

    out.sort(key=lambda x: x["severity"], reverse=True)
    return {"items": out[:cap], "count": len(out)}


# ══════════════════════════════════════════════════════════════════════════
# P9 · Working capital — "where is my cash locked?"
# ══════════════════════════════════════════════════════════════════════════

def get_working_capital(conn, company_id: str) -> dict:
    """Inventory + receivables − payables. Payables are only as good as the
    purchase data we have: without vendor bill due dates this is an open-PO
    commitment, not true AP, and the card says so."""
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(SUM(total_value),0) FROM canon_inventory_flat WHERE company_id=%s",
                    (company_id,))
        inventory = float(cur.fetchone()[0] or 0)
        cur.execute("""SELECT COALESCE(SUM(outstanding_amount),0) FROM canon_ar_flat
                       WHERE company_id=%s AND COALESCE(outstanding_amount,0) > 0""", (company_id,))
        receivables = float(cur.fetchone()[0] or 0)
        cur.execute("""SELECT COALESCE(SUM(po_value),0) FROM canon_purchase_order_flat
                       WHERE company_id=%s AND COALESCE(pending_qty,0) > 0""", (company_id,))
        commitments = float(cur.fetchone()[0] or 0)
    locked = inventory + receivables
    ls = _last_sync(conn, "inventory_valuation", company_id)
    return {"inventory": inventory, "receivables": receivables,
            "open_commitments": commitments, "locked": locked,
            "net": locked - commitments, "has_true_ap": False,
            "last_synced_at": _fmt(ls), "stale": _is_stale(ls)}
