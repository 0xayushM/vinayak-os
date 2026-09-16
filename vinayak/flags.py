"""
flags.py
─────────
The first synapse: what Accounts knows, where Sales will see it.

The architecture's central claim is that the fields talk to each other rather
than sitting in separate dashboards. This is the first place that is actually
true. Accounts notices a customer has stopped paying; Sales finds out on the
quote screen, before the next order is taken. Without something in between,
each half of the business knows a thing the other needs and neither finds out
until an order ships to someone who was never going to pay for it.

A flag is a fact with a life, not a computed value, and the difference
matters. Recomputing "is this customer risky" on every page load would be
simpler and would lose the two things that make it usable: a person can
override it ("I know, the MD has agreed terms"), and you can answer "why was
this customer on hold in March".

Raising and clearing are deliberately asymmetric. A flag goes up on any one of
several signals, because missing a bad debt is expensive. It comes down only
when the cause is genuinely gone, because a flag that flickers teaches people
to ignore it.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

HOLD, WATCH = "hold", "watch"

# The signals that raise a flag, worst first. Each is a fact from the ledger,
# not a score — an owner has to be able to argue with the reason.
SIGNAL_BROKEN_PROMISE = "broken_promise"
SIGNAL_LADDER_TOP = "ladder_top"
SIGNAL_VERY_OLD = "very_old"
SIGNAL_EXPOSURE = "exposure"

# A balance this old is a hold on its own, whatever else is true.
VERY_OLD_DAYS = 120
# Share of the whole receivable book sitting with one customer.
EXPOSURE_SHARE_PCT = 25.0


def assess(*, customer: str, outstanding: float, oldest_days: int,
           exposure_share_pct: float, rung: int = 0,
           broken_promises: int = 0) -> dict | None:
    """Should this customer be flagged, and why — in one sentence.

    Pure. Returns None when nothing is wrong, otherwise the level, the reason
    a person will read, and the evidence behind it.

    Ordered by what a person would find most damning. A broken promise comes
    first because it is the only signal that involves the customer having said
    something and not done it; everything else is arithmetic about lateness.
    """
    ev = {"outstanding": outstanding, "oldest_days": oldest_days,
          "exposure_share_pct": round(exposure_share_pct, 1),
          "rung": rung, "broken_promises": broken_promises}

    if broken_promises >= 2:
        return {"level": HOLD, "signal": SIGNAL_BROKEN_PROMISE, "evidence": ev,
                "reason": (f"{customer} has broken {broken_promises} payment promises. "
                           f"They are not slow — they are not paying.")}
    if broken_promises == 1 and oldest_days >= 60:
        return {"level": HOLD, "signal": SIGNAL_BROKEN_PROMISE, "evidence": ev,
                "reason": (f"{customer} agreed a payment date and missed it, with the "
                           f"oldest balance now {oldest_days} days past due.")}
    if rung >= 4:
        return {"level": HOLD, "signal": SIGNAL_LADDER_TOP, "evidence": ev,
                "reason": (f"{customer} has reached the top of the collections ladder — "
                           f"four reminders, still unpaid.")}
    if oldest_days >= VERY_OLD_DAYS:
        return {"level": HOLD, "signal": SIGNAL_VERY_OLD, "evidence": ev,
                "reason": (f"{customer} has a balance {oldest_days} days past due.")}
    if exposure_share_pct >= EXPOSURE_SHARE_PCT:
        return {"level": WATCH, "signal": SIGNAL_EXPOSURE, "evidence": ev,
                "reason": (f"{exposure_share_pct:.0f}% of everything owed to you sits with "
                           f"{customer}. Not late — concentrated.")}
    if rung >= 2 and oldest_days >= 45:
        return {"level": WATCH, "signal": SIGNAL_LADDER_TOP, "evidence": ev,
                "reason": (f"{customer} has had {rung} reminders and the oldest balance is "
                           f"{oldest_days} days past due.")}
    return None


# ── stored ────────────────────────────────────────────────────────────────

def live(conn, company_id: str, customers: list[str] | None = None) -> dict[str, dict]:
    """Live flags, keyed by customer — what Sales needs to decorate a screen."""
    sql = """SELECT customer_ref, level, reason, evidence, source, raised_at, overridden
               FROM customer_flags
              WHERE company_id = %s AND cleared_at IS NULL"""
    params: list = [company_id]
    if customers:
        sql += " AND customer_ref = ANY(%s)"
        params.append(customers)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return {r[0]: {"customer_ref": r[0], "level": r[1], "reason": r[2],
                   "evidence": r[3] or {}, "source": r[4],
                   "raised_at": r[5].isoformat() if r[5] else None,
                   "overridden": bool(r[6])} for r in rows}


def raise_flag(conn, company_id: str, customer_ref: str, verdict: dict, *,
               source: str = "agent") -> str | None:
    """Raise or upgrade a flag. Returns the id when something changed.

    An overridden flag is left alone — a person has said they know better, and
    a machine that keeps re-raising over the top of that is one people learn to
    switch off. A flag is only ever upgraded (watch → hold), never quietly
    downgraded: coming down is `clear`, which is a decision with a reason.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, level, overridden FROM customer_flags
                WHERE company_id = %s AND customer_ref = %s AND cleared_at IS NULL""",
            (company_id, customer_ref))
        existing = cur.fetchone()

        if existing:
            flag_id, level, overridden = existing
            if overridden:
                return None
            if level == HOLD or verdict["level"] == level:
                return None                      # already at least this serious
            cur.execute(
                """UPDATE customer_flags
                      SET level = %s, reason = %s, evidence = %s, raised_at = NOW()
                    WHERE id = %s""",
                (verdict["level"], verdict["reason"],
                 json.dumps(verdict.get("evidence", {}), default=str), flag_id))
            conn.commit()
            return str(flag_id)

        cur.execute(
            """INSERT INTO customer_flags (company_id, customer_ref, level, reason,
                                           evidence, source)
               VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
            (company_id, customer_ref, verdict["level"], verdict["reason"],
             json.dumps(verdict.get("evidence", {}), default=str), source))
        new_id = str(cur.fetchone()[0])
    conn.commit()
    return new_id


def clear(conn, company_id: str, customer_ref: str, *, by: str,
          reason: str | None = None) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE customer_flags
                  SET cleared_at = NOW(), cleared_by = %s, clear_reason = %s
                WHERE company_id = %s AND customer_ref = %s AND cleared_at IS NULL""",
            (by, reason, company_id, customer_ref))
        n = cur.rowcount or 0
    conn.commit()
    return bool(n)


def override(conn, company_id: str, customer_ref: str, *, by: str,
             note: str | None = None) -> bool:
    """A person knows something the ledger does not. Keep the flag on record,
    stop it driving anything, and remember who said so."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE customer_flags
                  SET overridden = TRUE, overridden_by = %s,
                      clear_reason = COALESCE(%s, clear_reason)
                WHERE company_id = %s AND customer_ref = %s AND cleared_at IS NULL""",
            (by, note, company_id, customer_ref))
        n = cur.rowcount or 0
    conn.commit()
    return bool(n)


def history(conn, company_id: str, customer_ref: str, limit: int = 20) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT level, reason, source, raised_at, cleared_at, cleared_by,
                      clear_reason, overridden
                 FROM customer_flags
                WHERE company_id = %s AND customer_ref = %s
                ORDER BY raised_at DESC LIMIT %s""",
            (company_id, customer_ref, limit))
        rows = cur.fetchall()
    return [{"level": r[0], "reason": r[1], "source": r[2],
             "raised_at": r[3].isoformat() if r[3] else None,
             "cleared_at": r[4].isoformat() if r[4] else None,
             "cleared_by": r[5], "clear_reason": r[6], "overridden": bool(r[7])}
            for r in rows]
