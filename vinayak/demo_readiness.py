"""
demo_readiness.py
──────────────────
Would the month-3 demo pass if it were held this morning?

`docs/reference/PLAN.md` §4 proposes nine criteria for the 1 Dec 2026 demo, all
to be shown live on Sandeep's own data. Most of them are counts that already
sit in the database — briefs delivered, watchers run unattended, actions
executed, experiments closed, active days — and a demo gate that is only
checked on the day is a gate that fails on the day. So this reads each one now,
and says for each how far it is from the line.

Two of the nine cannot be counted (a Pulse "in his role's order", a wiki that is
"current"); they are reported as `manual`, never as passed, so the readiness
line cannot look better than it is.

    python -m vinayak.scripts.milestone_status --demo

`assess` is pure — facts in, verdicts out — so the thresholds are argued with
in tests/test_demo_readiness.py rather than in the demo.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from vinayak import experiments as X
from vinayak import usage as U

logger = logging.getLogger(__name__)

# The §4 thresholds, stated once.
BRIEF_DAYS = 30          # calendar days looked back; brief.py counts the working days in them
MIN_WATCHERS_UNATTENDED = 3
MIN_ACTIONS_EXECUTED = 10
MIN_EXPERIMENTS_LOGGED = 10
MIN_EXPERIMENTS_CLOSED = 5
USAGE_WEEKS = 4
MIN_EVAL_CASES = 40
INCIDENT_FREE_DAYS = 30

# The watchers that count as "running unattended" in §4 are the ones that look
# at the business, not the housekeeping that turns their findings into Inbox
# items or closes experiments.
DETECTOR_KEYS = ("detect.overdue_rung", "detect.promise_broken", "detect.credit_flag",
                 "detect.data_stale", "detect.anomaly")

MET, SHORT, MANUAL = "met", "short", "manual"


def _row(key: str, criterion: str, state: str, where: str) -> dict:
    return {"key": key, "criterion": criterion, "state": state, "where": where}


def assess(f: dict) -> list[dict]:
    """Pure: the gathered facts in, one verdict per §4 criterion out.

    A fact that could not be read (None) is `short`, never `met` — a table that
    is missing on production is exactly the thing to find out before 1 Dec."""
    rows: list[dict] = []

    rows.append(_row(
        "pulse", "Pulse in his role's order, with freshness and confidence on every card",
        MANUAL, "Shown live; check on the rehearsal."))

    b = f.get("brief")
    crit = "Brief delivered every working day for the previous 30 days"
    if not f.get("tracked_user"):
        rows.append(_row("brief", crit, SHORT,
                         "No tracked user, so there is nobody whose inbox to count."))
    elif b is None:
        rows.append(_row("brief", crit, SHORT,
                         "No delivery log to read (migration 024 not applied?)."))
    else:
        missed = b.get("missed") or []
        rows.append(_row("brief", crit, MET if b["every_working_day"] else SHORT,
                         f"{b['delivered_working_days']} of {b['expected_working_days']} working days "
                         f"delivered to {f['tracked_user']}"
                         + (f" · last missed {missed[-1]}." if missed else ".")))

    w, a = f.get("watchers_unattended"), f.get("actions_executed")
    ok = (w or 0) >= MIN_WATCHERS_UNATTENDED and (a or 0) >= MIN_ACTIONS_EXECUTED \
        and (f.get("agent_proposals") or 0) > 0
    rows.append(_row(
        "brain", "≥ 3 watchers unattended with Inbox items; ≥ 10 actions approved and executed",
        MET if ok else SHORT,
        f"{w or 0} watchers ran on schedule in the last 7 days · "
        f"{f.get('agent_proposals') or 0} proposals from the brain · "
        f"{a or 0} of {MIN_ACTIONS_EXECUTED} actions executed."))

    c = f.get("chases_logged") or 0
    rows.append(_row("collections", "Collections proof shows recovery against chases sent",
                     MET if c > 0 else SHORT,
                     f"{c} chases logged as sent" + ("" if c else
                     " — the proof card has nothing to measure until one is.")))

    fl = f.get("active_flags") or 0
    rows.append(_row("credit", "Credit gate shows on Quotes and Orders for a flagged customer",
                     MET if fl > 0 else SHORT, f"{fl} customers currently flagged."))

    x = f.get("experiments") or {}
    logged, closed = x.get("logged", 0), x.get("with_outcomes", 0)
    ai = x.get("ai_suggested", 0)
    ok = logged >= MIN_EXPERIMENTS_LOGGED and closed >= MIN_EXPERIMENTS_CLOSED \
        and ai * 2 >= logged
    rows.append(_row(
        "experiments", "≥ 10 experiments logged, ≥ 5 with outcomes, at least half AI-suggested",
        MET if ok else SHORT,
        f"{logged} logged · {closed} of {MIN_EXPERIMENTS_CLOSED} with outcomes · "
        f"{ai} AI-suggested · {x.get('running', 0)} running, {x.get('proposed', 0)} awaiting a decision."))

    weeks = f.get("usage_weeks")
    if not f.get("tracked_user"):
        rows.append(_row("usage", "Active ≥ 4 days in each of the previous 4 weeks", SHORT,
                         "No tracked user set (`milestone_user_email`)."))
    else:
        weeks = weeks or []
        good = sum(1 for wk in weeks if wk["qualifies"])
        rows.append(_row("usage", "Active ≥ 4 days in each of the previous 4 weeks",
                         MET if len(weeks) == USAGE_WEEKS and good == USAGE_WEEKS else SHORT,
                         f"{good} of {USAGE_WEEKS} complete weeks qualify ("
                         + ", ".join(str(wk["active_days"]) for wk in weeks) + " active days)."))

    evals = {e["runner"]: e for e in (f.get("evals") or [])}
    missing = [r for r in ("engine", "native") if r not in evals]
    failing = [r for r, e in evals.items() if r in ("engine", "native")
               and (e["cases_run"] < MIN_EVAL_CASES or e["citation_compliance"] < 1.0)]
    rows.append(_row(
        "eval", "Eval passes on both paths, 100% citation, ≥ 40 questions",
        MET if not missing and not failing else SHORT,
        " · ".join(f"{r}: {e['cases_run']} cases, citation {e['citation_compliance']:.0%} "
                   f"({e['ran_at'][:10]})" for r, e in sorted(evals.items()))
        + (f" · no recorded run for {', '.join(missing)}" if missing else "")))

    inc = f.get("critical_30d")
    rows.append(_row("incidents", "No critical incident in the previous 30 days; wiki current",
                     MANUAL if inc == 0 else SHORT,
                     ("none recorded — the wiki still needs a look" if inc == 0 else
                      f"{inc} critical incidents recorded" if inc else "could not read incidents")))
    return rows


def complete_weeks(weekly: dict, n: int = USAGE_WEEKS) -> list[dict]:
    """The last `n` complete weeks from usage.weekly_summary, oldest first."""
    return [w for w in weekly.get("weeks", []) if not w["partial"]][-n:]


def _scalar(conn, sql: str, params: tuple):
    """One number, or None when the table is not there yet. A readiness check
    that crashes on a missing migration tells you less than one that says so."""
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            r = cur.fetchone()
        return int(r[0] or 0) if r else 0
    except Exception as exc:  # noqa: BLE001
        logger.info("demo readiness: %s", exc)
        conn.rollback()
        return None


def _brief(conn, company_id: str, recipient: str, today: date) -> dict | None:
    """Working days delivered, counted the way brief.py counts them (Mon–Sat),
    or None when the delivery log does not exist yet."""
    from vinayak.brief import delivery_days
    try:
        return delivery_days(conn, company_id, recipient, days=BRIEF_DAYS, today=today)
    except Exception as exc:  # noqa: BLE001
        logger.info("demo readiness: %s", exc)
        conn.rollback()
        return None


def gather(conn, company_id: str, tracked_user: str, evals: list[dict],
           today: date | None = None) -> dict:
    today = today or date.today()
    since_7 = today - timedelta(days=7)
    f: dict = {"tracked_user": tracked_user, "evals": evals}

    if tracked_user:
        f["brief"] = _brief(conn, company_id, tracked_user, today)
        days = U.active_days(conn, tracked_user, today - timedelta(days=7 * (USAGE_WEEKS + 1) + 7))
        f["usage_weeks"] = complete_weeks(U.weekly_summary(days, today))

    f["watchers_unattended"] = _scalar(
        conn,
        """SELECT COUNT(DISTINCT workflow_key) FROM brain_runs
            WHERE company_id = %s AND trigger = 'schedule' AND status = 'ok'
              AND workflow_key = ANY(%s) AND started_at >= %s""",
        (company_id, list(DETECTOR_KEYS), since_7))
    f["agent_proposals"] = _scalar(
        conn, "SELECT COUNT(*) FROM actions WHERE company_id = %s AND event_id IS NOT NULL",
        (company_id,))
    f["actions_executed"] = _scalar(
        conn, "SELECT COUNT(*) FROM actions WHERE company_id = %s AND status = 'executed'",
        (company_id,))
    f["chases_logged"] = _scalar(
        conn, "SELECT COUNT(*) FROM chase_log WHERE company_id = %s", (company_id,))
    f["active_flags"] = _scalar(
        conn,
        """SELECT COUNT(DISTINCT customer_ref) FROM customer_flags
            WHERE company_id = %s AND cleared_at IS NULL AND NOT overridden""",
        (company_id,))
    f["critical_30d"] = _scalar(
        conn,
        """SELECT COUNT(*) FROM incidents WHERE severity = 'critical'
              AND started_at >= NOW() - INTERVAL '30 days'
              AND (company_id = %s OR company_id IS NULL)""", (company_id,))
    f["experiments"] = X.counts(conn, company_id)
    return f


def as_markdown(company_id: str, rows: list[dict], today: date | None = None) -> str:
    today = today or date.today()
    mark = {MET: "✅", SHORT: "🟡", MANUAL: "⬜"}
    met = sum(1 for r in rows if r["state"] == MET)
    lines = [f"_Month-3 demo readiness, read on {today.isoformat()} from `{company_id}` — "
             f"{met} of {len(rows)} met, {sum(1 for r in rows if r['state'] == MANUAL)} "
             f"to check by hand._", "",
             "| | Criterion | Where it stands |", "|---|---|---|"]
    lines += [f"| {mark[r['state']]} | {r['criterion']} | {r['where']} |" for r in rows]
    return "\n".join(lines)
