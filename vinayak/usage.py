"""
usage.py
─────────
Usage evidence for Milestone 1: "the owner has used the dashboard at least
4 days per week for 60 consecutive days". Two jobs:

  • record(conn, company_id, user_email) — one row per (company, user, day),
    called from the workspace dependency on every authenticated business
    request. A small in-process set stops the same day being re-written on
    every request; the DB upsert makes it safe across processes anyway.

  • stats(conn, user_email, ...) — active days, per-week counts, and the
    longest run of consecutive qualifying weeks, expressed in days so the
    Milestone board can show "N / 60".

The qualifying rule, stated once so it is auditable:
  A week (Monday–Sunday) QUALIFIES when the user was active on ≥ 4 distinct
  days in it. A run is a sequence of consecutive qualifying weeks. The 60-day
  criterion is met when a run covers ≥ 60 days (9 consecutive qualifying
  weeks = 63 days; 8 weeks = 56 days does not meet it). The current, partial
  week is reported separately and never breaks a run until it ends.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_seen: set[tuple[str, str, date]] = set()
_SEEN_CAP = 5000


def record(conn, company_id: str, user_email: str, today: date | None = None) -> None:
    """Upsert today's usage row. Never raises — usage is evidence, not a gate."""
    if not company_id or not user_email:
        return
    today = today or date.today()
    key = (company_id, user_email.lower(), today)
    if key in _seen:
        return
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO usage_events (company_id, user_email, day)
                   VALUES (%s, %s, %s)
                   ON CONFLICT (company_id, user_email, day)
                   DO UPDATE SET last_seen = NOW(), requests = usage_events.requests + 1""",
                (company_id, user_email.lower(), today),
            )
        conn.commit()
        if len(_seen) > _SEEN_CAP:
            _seen.clear()
        _seen.add(key)
    except Exception as exc:  # noqa: BLE001
        logger.warning("usage.record failed for %s/%s: %s", company_id, user_email, exc)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass


def active_days(conn, user_email: str, since: date, company_id: str | None = None) -> list[date]:
    """Distinct days the user was active (any workspace unless company_id given)."""
    with conn.cursor() as cur:
        if company_id:
            cur.execute(
                "SELECT DISTINCT day FROM usage_events WHERE user_email = %s AND company_id = %s AND day >= %s ORDER BY day",
                (user_email.lower(), company_id, since),
            )
        else:
            cur.execute(
                "SELECT DISTINCT day FROM usage_events WHERE user_email = %s AND day >= %s ORDER BY day",
                (user_email.lower(), since),
            )
        return [r[0] for r in cur.fetchall()]


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_summary(days: list[date], today: date | None = None, min_days: int = 4) -> dict:
    """Pure: from a list of active days compute per-week counts and runs."""
    today = today or date.today()
    if not days:
        return {"weeks": [], "best_run_weeks": 0, "best_run_days": 0,
                "current_run_weeks": 0, "current_run_days": 0, "current_week": None,
                "meets_60_days": False}
    by_week: dict[date, set[date]] = {}
    for d in days:
        by_week.setdefault(_week_start(d), set()).add(d)
    first = _week_start(min(days))
    this_week = _week_start(today)
    weeks = []
    w = first
    while w <= this_week:
        n = len(by_week.get(w, ()))
        weeks.append({"week_start": w.isoformat(), "active_days": n,
                      "qualifies": n >= min_days, "partial": w == this_week})
        w += timedelta(days=7)

    # Runs over COMPLETE weeks only; the partial current week never breaks a run.
    complete = [x for x in weeks if not x["partial"]]
    best = cur = 0
    for x in complete:
        cur = cur + 1 if x["qualifies"] else 0
        best = max(best, cur)
    # current run = trailing qualifying complete weeks
    current = 0
    for x in reversed(complete):
        if x["qualifies"]:
            current += 1
        else:
            break
    return {
        "weeks": weeks[-16:],
        "best_run_weeks": best, "best_run_days": best * 7,
        "current_run_weeks": current, "current_run_days": current * 7,
        "current_week": weeks[-1] if weeks else None,
        "meets_60_days": best * 7 >= 60,
    }


def stats(conn, user_email: str, window_days: int = 120, company_id: str | None = None,
          today: date | None = None) -> dict:
    today = today or date.today()
    since = today - timedelta(days=window_days)
    days = active_days(conn, user_email, since, company_id)
    out = weekly_summary(days, today)
    out.update({
        "user_email": user_email.lower(),
        "window_days": window_days,
        "active_days_in_window": len(days),
        "last_active": days[-1].isoformat() if days else None,
    })
    return out


def users_seen(conn, company_id: str | None = None, window_days: int = 120) -> list[dict]:
    """Who has been active recently, with day counts — for the Milestone board."""
    since = date.today() - timedelta(days=window_days)
    with conn.cursor() as cur:
        if company_id:
            cur.execute(
                """SELECT user_email, COUNT(DISTINCT day), MAX(day)
                   FROM usage_events WHERE company_id = %s AND day >= %s
                   GROUP BY user_email ORDER BY 2 DESC""", (company_id, since))
        else:
            cur.execute(
                """SELECT user_email, COUNT(DISTINCT day), MAX(day)
                   FROM usage_events WHERE day >= %s
                   GROUP BY user_email ORDER BY 2 DESC""", (since,))
        return [{"user_email": r[0], "active_days": int(r[1]),
                 "last_active": r[2].isoformat() if r[2] else None} for r in cur.fetchall()]
