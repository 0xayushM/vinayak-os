"""
group.py
─────────
The whole group on one screen.

Sandeep does not run a company; he runs nine. A dashboard scoped to one brand
asks him to open it nine times and hold the comparison in his head, which is
precisely the thing he already does badly and the reason he wanted this built.
One row per company, the same five figures, ranked so the one that needs him
is at the top — that is the version he opens every morning, and criterion 2's
sixty-day clock depends on there being a reason to.

Two design decisions worth stating:

**Every figure here already exists.** Nothing is computed a second way for the
group view; it reads the same query functions the single-company pages read.
A group total that disagrees with the sum of its parts is the fastest way to
lose the room, and the only reliable defence is not having two code paths.

**A company that cannot be read says so.** A failed brand shows an error in
its row rather than a zero, and the group total says how many it is missing.
A zero in a revenue column reads as "a bad month", which is a different and
much worse lie than "I could not read this".
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _row(conn, company_id: str, name: str) -> dict:
    from vinayak.schema import pulse as P
    from vinayak.schema.queries import get_ar_summary

    row: dict = {"company_id": company_id, "name": name, "error": None}
    try:
        # Key names taken from get_ar_summary itself, not guessed. The first
        # version of this read `overdue_amount`, got None, and showed a
        # confident ₹0 overdue for a company with ₹2.85Cr past due — a zero is
        # a worse lie than a blank because nobody questions it.
        ar = get_ar_summary(conn, company_id)
        outstanding = float(ar.get("total_outstanding") or 0)
        overdue = float(ar.get("overdue_value") or 0)
        row["outstanding"] = outstanding
        row["overdue"] = overdue
        row["overdue_count"] = int(ar.get("overdue_count") or 0)
        row["overdue_pct"] = round(overdue / outstanding * 100, 1) if outstanding else 0.0

        cash = P.get_cash_30d(conn, company_id)
        row["cash_net_30d"] = float(cash.get("net") or 0)
        row["stale"] = bool(cash.get("stale"))

        week = P.get_week_delta(conn, company_id)
        row["week"] = float(week.get("this_week") or 0)
        row["week_delta_pct"] = float(week.get("delta_pct") or 0)

        drift = P.get_aging_drift(conn, company_id)
        row["drift"] = 0.0 if drift.get("history_building") else float(drift.get("drift") or 0)
        row["drift_building"] = bool(drift.get("history_building"))

        with conn.cursor() as cur:
            cur.execute("""SELECT COUNT(*) FROM actions
                            WHERE company_id = %s AND status = 'proposed'""", (company_id,))
            row["inbox"] = int(cur.fetchone()[0] or 0)
            cur.execute("""SELECT COUNT(*) FROM customer_flags
                            WHERE company_id = %s AND cleared_at IS NULL
                              AND level = 'hold' AND overridden = FALSE""", (company_id,))
            row["holds"] = int(cur.fetchone()[0] or 0)
    except Exception as exc:  # noqa: BLE001 — one unreadable brand must not blank the group
        conn.rollback()
        logger.warning("group: %s could not be read: %s", company_id, exc)
        row["error"] = str(exc)[:200]
    return row


def _attention(row: dict) -> float:
    """What puts a company at the top of the list.

    Overdue money dominates because it is the thing an owner can act on today;
    drift and a full inbox nudge. Deliberately crude — the ordering only has to
    be defensible, and anything cleverer becomes a score nobody can argue with.
    """
    if row.get("error"):
        return float("inf")          # unreadable is the most urgent thing there is
    return (row.get("overdue", 0.0)
            + max(0.0, row.get("drift", 0.0)) * 2
            + row.get("inbox", 0) * 50_000
            + row.get("holds", 0) * 100_000)


def overview(conn, companies: list[tuple[str, str]]) -> dict:
    """One row per company, most in need of attention first."""
    rows = [_row(conn, cid, name) for cid, name in companies]
    rows.sort(key=_attention, reverse=True)
    readable = [r for r in rows if not r.get("error")]
    return {
        "companies": rows,
        "count": len(rows),
        "unreadable": len(rows) - len(readable),
        "totals": {
            "outstanding": round(sum(r.get("outstanding", 0) for r in readable), 2),
            "overdue": round(sum(r.get("overdue", 0) for r in readable), 2),
            "cash_net_30d": round(sum(r.get("cash_net_30d", 0) for r in readable), 2),
            "week": round(sum(r.get("week", 0) for r in readable), 2),
            "inbox": sum(r.get("inbox", 0) for r in readable),
            "holds": sum(r.get("holds", 0) for r in readable),
        },
        # Said explicitly so a total is never read as covering companies it does
        # not. Summing four of nine and calling it the group is how a number
        # becomes a lie without anyone writing one.
        "totals_cover": len(readable),
    }
