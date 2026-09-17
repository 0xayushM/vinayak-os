"""
milestones.py
──────────────
The live numbers behind each Milestone-1 criterion.

The tracker itself is a document — docs/reference/MILESTONES.md — because a
milestone review is a conversation with Shourya and Sandeep, not a screen, and
a document can hold the things a table cannot: what was agreed, what changed,
and why a criterion is judged the way it is.

What a document cannot do is count. So this module computes the countable half
— active days, experiments with outcomes, eval scores, incidents — and
`python -m vinayak.scripts.milestone_status` prints it as a markdown block to
paste into the doc. The numbers stay honest; the judgement stays written down.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

from vinayak import experiments as X
from vinayak import usage as U
from vinayak.eval import frozen as F
from vinayak.eval.cases import CASES

# The runners criterion 3 must hold on: the deterministic engine, and the
# native agent path production actually answers with.
CRITERION_RUNNERS = ("engine", "native")

DEFAULT_START = date(2026, 9, 1)


def month_end(start: date, months: int) -> date:
    """The same calendar day `months` later, clamped to 28 so month lengths
    never move a review date."""
    y, m = start.year, start.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, min(start.day, 28))


def _setting(conn, key: str, default: str = "") -> str:
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM platform_settings WHERE key = %s", (key,))
            r = cur.fetchone()
        return r[0] if r else default
    except Exception:  # noqa: BLE001 — the table may predate migration 020
        conn.rollback()
        return default


def dates(start: date | None = None) -> dict:
    start = start or DEFAULT_START
    today = date.today()
    return {"start": start.isoformat(),
            "month_3_demo": month_end(start, 3).isoformat(),
            "month_6_review": month_end(start, 6).isoformat(),
            "month_8_latest": month_end(start, 8).isoformat(),
            "month_12_review": month_end(start, 12).isoformat(),
            "month_24_review": month_end(start, 24).isoformat(),
            "days_to_month_6": (month_end(start, 6) - today).days}


def freeze_status(manifest: dict[str, str] | None = None,
                  cases: list[dict] | None = None) -> dict:
    """Where the eval freeze stands, from code alone — no database."""
    manifest = F.FROZEN if manifest is None else manifest
    cases = CASES if cases is None else cases
    return {"frozen": bool(manifest),
            "frozen_on": F.FROZEN_ON if manifest is F.FROZEN else None,
            "size": len(manifest),
            "hash": F.manifest_hash(manifest),
            "problems": F.check_frozen(manifest, cases),
            "candidates": len(cases),
            "verified": sum(1 for c in cases if F.is_verified(c))}


def status(conn, company_id: str) -> dict:
    """Every countable Milestone-1 criterion, with the number behind it."""
    start_s = _setting(conn, "milestone_start_date", DEFAULT_START.isoformat())
    try:
        start = date.fromisoformat(start_s)
    except ValueError:
        start = DEFAULT_START
    tracked = _setting(conn, "milestone_user_email", "") or ""

    usage = U.stats(conn, tracked, window_days=200) if tracked else None

    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (runner) runner, ran_at, cases_run, passed,
                      citation_compliance, factual_accuracy, ship_blocked
               FROM eval_runs ORDER BY runner, ran_at DESC""")
        evals = [{"runner": r[0], "ran_at": r[1].isoformat(), "cases_run": r[2],
                  "passed": r[3], "citation_compliance": float(r[4]),
                  "factual_accuracy": float(r[5]) if r[5] is not None else None,
                  "ship_blocked": bool(r[6])} for r in cur.fetchall()]

    # Criterion 3 is judged on the frozen set, so the latest FROZEN run per
    # runner is read separately from the latest run of any kind — a candidates
    # run recorded yesterday must not stand in for it. Only runs covering this
    # workspace (its own, or all workspaces) count.
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (runner) runner, ran_at, company_id, metrics
               FROM eval_runs
               WHERE metrics->>'set' = 'frozen' AND (company_id = %s OR company_id IS NULL)
               ORDER BY runner, ran_at DESC""", (company_id,))
        frozen_evals = [{"runner": r[0], "ran_at": r[1].isoformat(), "company_id": r[2],
                         "metrics": r[3] if isinstance(r[3], dict) else json.loads(r[3])}
                        for r in cur.fetchall()]

    counts = X.counts(conn, company_id)

    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*), MAX(started_at) FROM incidents
                WHERE severity = 'critical' AND started_at >= NOW() - INTERVAL '60 days'
                  AND (company_id = %s OR company_id IS NULL)""", (company_id,))
        critical, last_critical = cur.fetchone()
    days_since_critical = ((datetime.now(timezone.utc) - last_critical).days
                           if last_critical else None)

    return {
        "company_id": company_id,
        "dates": dates(start),
        "tracked_user": tracked,
        "usage": usage,
        "evals": evals,
        "eval_freeze": freeze_status(),
        "frozen_evals": frozen_evals,
        "experiments": counts,
        "incidents": {"critical_60d": int(critical or 0),
                      "days_since_critical": days_since_critical},
    }


def _frozen_run_verdict(runner: str, run: dict | None, current_hash: str | None) -> str:
    if run is None:
        return f"`{runner}` no frozen run recorded (`--frozen --record`)"
    m = run["metrics"]
    when = run["ran_at"][:10]
    if m.get("frozen_hash") != current_hash:
        return f"`{runner}` last frozen run ({when}) was on an earlier freeze — re-run"
    fa = m.get("factual_accuracy")
    figures = (f"factual {f'{fa:.0%}' if fa is not None else 'not graded'}, "
               f"citation {m.get('citation_compliance', 0):.0%}")
    verdict = "met" if F.criterion_met(m, current_hash) else "NOT met"
    return f"`{runner}` {verdict} ({figures}, {when})"


def _with_freeze(eval_line: str, freeze: dict | None, frozen_evals: list[dict]) -> str:
    """The eval line with the freeze's standing added.

    Before anything is frozen or verified this returns the line unchanged —
    there is nothing to add, and a status block that grows words for an
    absent thing reads as progress. Once cases are verified it says how many.
    Once the set is frozen, the line leads with the freeze and then gives the
    criterion's verdict on the latest frozen run for each runner that must
    pass — the engine AND the native path production uses — because a score
    on one path is not the criterion.
    """
    if not freeze or (not freeze.get("frozen") and not freeze.get("verified")):
        return eval_line
    if not freeze.get("frozen"):
        return (f"{eval_line} · not frozen yet · "
                f"{freeze['verified']} of {freeze['candidates']} cases verified")

    head = (f"frozen at {freeze['size']} on {freeze.get('frozen_on') or '—'} "
            f"(hash `{freeze['hash']}`)")
    if freeze.get("problems"):
        head += f" · **freeze drifted: {len(freeze['problems'])} problem(s)**"
    by_runner = {r["runner"]: r for r in frozen_evals}
    verdicts = " · ".join(_frozen_run_verdict(name, by_runner.get(name), freeze["hash"])
                          for name in CRITERION_RUNNERS)
    return (f"{head} · {freeze['verified']} of {freeze['candidates']} cases verified · "
            f"criterion: {verdicts} · latest any run: {eval_line}")


def as_markdown(s: dict) -> str:
    """The block that goes into docs/reference/MILESTONES.md under
    "Where the numbers stand"."""
    d = s["dates"]
    u = s["usage"]
    x = s["experiments"]
    best_eval = max(s["evals"], key=lambda e: e["cases_run"], default=None) if s["evals"] else None

    usage_line = (
        f"{u['best_run_days']} of 60 consecutive days (tracking {s['tracked_user']}; "
        f"{u['active_days_in_window']} active days recorded)"
        if u else "no tracked user set (`milestone_user_email` in `platform_settings`)")

    if best_eval:
        fa = best_eval["factual_accuracy"]
        n = best_eval["cases_run"]
        # The criterion is a set FIXED at 50. Carrying more than that before the
        # freeze is the plan, not an overshoot — so say which it is rather than
        # printing "58 of 50", which reads like a bug.
        size = f"{n} cases (freeze at 50)" if n > 50 else f"{n} of 50 cases"
        eval_line = (f"{size} · citation {best_eval['citation_compliance']:.0%} · "
                     f"factual {f'{fa:.0%}' if fa is not None else 'not graded yet'} "
                     f"(runner `{best_eval['runner']}`, {best_eval['ran_at'][:10]})")
    else:
        eval_line = "no harness run recorded yet (`python -m vinayak.eval.harness --record`)"
    eval_line = _with_freeze(eval_line, s.get("eval_freeze"), s.get("frozen_evals") or [])

    inc = s["incidents"]
    inc_line = (f"{inc['critical_60d']} critical in the last 60 days"
                if inc["critical_60d"] else "none recorded in the last 60 days")

    return "\n".join([
        f"_Read on {date.today().isoformat()} from workspace `{s['company_id']}`._",
        "",
        f"| Criterion | Where it stands |",
        f"|---|---|",
        f"| Owner active ≥ 4 days/week for 60 consecutive days | {usage_line} |",
        f"| 50-question eval: ≥ 80% factual, 100% citation | {eval_line} |",
        f"| ≥ 30 logged experiments with outcomes | {x['with_outcomes']} with outcomes of "
        f"{x['logged']} logged · {x['ai_suggested']} AI-suggested, {x['ai_suggested_acted_on']} acted on |",
        f"| No critical incident in the last 60 days | {inc_line} |",
        "",
        f"Month-3 demo **{d['month_3_demo']}** · month-6 review **{d['month_6_review']}** "
        f"({d['days_to_month_6']} days away) · latest acceptable **{d['month_8_latest']}**.",
    ])
