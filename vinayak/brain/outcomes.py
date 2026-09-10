"""
brain/outcomes.py
──────────────────
Closes experiments whose window has ended, by reading the metric again.

This is the file that makes the experiments log worth keeping. An experiment
that is started and never closed proves nothing, and asking a busy owner to
come back six weeks later and record a result is asking for thirty blank
rows. So the window is decided when the experiment starts, and when it ends
the metric is read the same way it was read at the baseline.

The verdict rule is deliberately dumb and stated once:

    moved to at least the target        → positive
    moved the wrong way from baseline
      by more than the noise floor      → negative
    anything else, or unreadable        → inconclusive

'Inconclusive' is a real outcome, not a failure to have one. Most business
experiments end there, and a log that pretends otherwise is a log nobody will
trust when it does say 'positive'.

Direction comes from brain/metrics.py, never from the sign of the change:
overdue money falling is good, revenue falling is not, and only the metric
knows which it is.
"""
from __future__ import annotations

import logging

from vinayak.brain import metrics

logger = logging.getLogger(__name__)

# A move smaller than this share of the baseline is noise, not a result.
NOISE_FLOOR_PCT = 5.0

# With no explicit target, "better by at least this much" counts as positive.
DEFAULT_TARGET_IMPROVEMENT_PCT = 10.0


def verdict(baseline: float | None, result: float | None, *,
            lower_is_better: bool, target: float | None = None) -> tuple[str, str]:
    """Pure. Returns (outcome, one-sentence reason)."""
    if baseline is None or result is None:
        return "inconclusive", "The metric could not be read at both ends of the window."
    if baseline == 0:
        return ("inconclusive",
                "The metric started at zero, so there was nothing to move.")

    change = result - baseline
    improvement = -change if lower_is_better else change
    improvement_pct = improvement / abs(baseline) * 100

    if target is not None:
        met = result <= target if lower_is_better else result >= target
        if met:
            return "positive", f"Reached the target of {target:g}."

    if improvement_pct >= DEFAULT_TARGET_IMPROVEMENT_PCT:
        return "positive", f"Moved {improvement_pct:.0f}% in the right direction."
    if improvement_pct <= -NOISE_FLOOR_PCT:
        return "negative", f"Moved {abs(improvement_pct):.0f}% the wrong way."
    return "inconclusive", f"Moved {improvement_pct:+.0f}% — inside the noise."


def close_due(conn, company_id: str) -> dict:
    """Close every running experiment whose window has ended."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, title, metric_key, entity_ref, baseline, target
                 FROM experiments
                WHERE company_id = %s AND status = 'running'
                  AND auto_close = TRUE
                  AND ends_at IS NOT NULL AND ends_at <= CURRENT_DATE
                  AND metric_key IS NOT NULL""", (company_id,))
        rows = cur.fetchall()

    closed = 0
    outcomes: list[dict] = []
    for exp_id, title, metric_key, entity_ref, baseline, target in rows:
        m = metrics.METRICS.get(metric_key)
        result = metrics.read(conn, company_id, metric_key, entity_ref)
        out, reason = verdict(
            float(baseline) if baseline is not None else None,
            result,
            lower_is_better=m.lower_is_better if m else True,
            target=float(target) if target is not None else None,
        )
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE experiments
                      SET status = 'closed', result = %s, outcome = %s,
                          outcome_notes = %s, closed_at = NOW(),
                          decided_by = COALESCE(decided_by, 'agent'), updated_at = NOW()
                    WHERE id = %s""",
                (result, out, f"Closed automatically. {reason}", exp_id))
        conn.commit()
        closed += 1
        outcomes.append({"id": str(exp_id), "title": title, "outcome": out,
                         "baseline": float(baseline) if baseline is not None else None,
                         "result": result, "reason": reason})

    return {"closed": closed, "outcomes": outcomes,
            "summary": (f"{closed} experiment{'s' if closed != 1 else ''} closed with an outcome."
                        if closed else "No experiment windows ended today.")}


def start_accepted(conn, company_id: str) -> int:
    """An accepted experiment that never started is a dead row.

    Starting one re-reads its baseline and re-dates its window from today,
    rather than keeping the figures captured when it was suggested. A
    suggestion accepted three weeks late would otherwise be judged against a
    stale baseline over a window that had already half expired.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, metric_key, entity_ref, window_days
                 FROM experiments
                WHERE company_id = %s AND status = 'accepted'""", (company_id,))
        rows = cur.fetchall()

    for exp_id, metric_key, entity_ref, window_days in rows:
        baseline = (metrics.read(conn, company_id, metric_key, entity_ref)
                    if metric_key else None)
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE experiments
                      SET status = 'running',
                          started_at = CURRENT_DATE,
                          ends_at = CURRENT_DATE + COALESCE(%s, 30),
                          baseline = COALESCE(%s, baseline),
                          updated_at = NOW()
                    WHERE id = %s""",
                (window_days, baseline, exp_id))
        conn.commit()
    return len(rows)
