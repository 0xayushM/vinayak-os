"""
brain/registry.py
──────────────────
What watchers exist, what each one does, and how often it should run.

Code declares the watcher; the `workflows` table decides whether it runs for
a given company and with what thresholds. That split is deliberate: turning
a noisy watcher off for one company is an UPDATE, not a deploy, and a new
company gets the defaults below the first time the worker sees it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class Watcher:
    key: str
    title: str
    what_it_does: str          # one sentence, shown on the Business Brain page
    interval_minutes: int
    fn: Callable               # (conn, company_id, *, run_id, config) -> dict | int
    default_config: dict = field(default_factory=dict)


def _wrap_detector(fn):
    """A detector returns a count; the runner wants a dict."""
    def run(conn, company_id, *, run_id=None, config=None):
        n = fn(conn, company_id, run_id=run_id, config=config)
        return {"events_emitted": n}
    return run


def all_watchers() -> list[Watcher]:
    # Imported here so the registry can be read (by tests, by the API) without
    # dragging the whole query layer in.
    from vinayak.brain import consumer, detectors, outcomes, strategy

    return [
        Watcher(
            key="detect.overdue_rung",
            title="Collections ladder",
            what_it_does=("Watches every unpaid invoice and raises one event the "
                          "first time it passes 7, 30, 60 and 90 days late."),
            interval_minutes=180,
            fn=_wrap_detector(detectors.detect_overdue_rung),
            default_config={"min_amount": detectors.MIN_CHASE_AMOUNT,
                            "max_per_pass": detectors.MAX_RUNG_EVENTS_PER_PASS},
        ),
        Watcher(
            key="detect.data_stale",
            title="Feed health",
            what_it_does=("Raises an event once a day for any feed that has not "
                          "synced successfully in over a day."),
            interval_minutes=180,
            fn=_wrap_detector(detectors.detect_data_stale),
            default_config={"stale_hours": detectors.STALE_HOURS},
        ),
        Watcher(
            key="detect.anomaly",
            title="Anomaly watch",
            what_it_does=("Raises an event for negative stock, an invoice far above "
                          "a customer's own normal, or a vendor price jump."),
            interval_minutes=360,
            fn=_wrap_detector(detectors.detect_anomaly),
            default_config={"min_severity": 40},
        ),
        Watcher(
            key="brain.consume",
            title="Act on what was found",
            what_it_does=("Turns pending events into proposals in the approval "
                          "inbox, and closes the ones that need no action."),
            interval_minutes=30,
            fn=lambda conn, company_id, *, run_id=None, config=None:
                _consume_result(consumer.consume(conn, company_id)),
        ),
        Watcher(
            key="strategy.weekly",
            title="Weekly suggestions",
            what_it_does=("Reads the Pulse once a week and proposes experiments "
                          "worth trying, each with a metric and a window."),
            interval_minutes=60 * 24 * 7,
            fn=lambda conn, company_id, *, run_id=None, config=None:
                strategy.suggest(conn, company_id, config=config),
            default_config={"max_suggestions": 6},
        ),
        Watcher(
            key="experiments.close",
            title="Close finished experiments",
            what_it_does=("Reads the metric for every experiment whose window has "
                          "ended and records the outcome."),
            interval_minutes=60 * 12,
            fn=lambda conn, company_id, *, run_id=None, config=None:
                _close_and_start(outcomes, conn, company_id),
        ),
    ]


def _close_and_start(outcomes, conn, company_id) -> dict:
    """Starting accepted experiments and closing finished ones is one pass:
    both are the same question — has anything crossed a line since yesterday?"""
    started = outcomes.start_accepted(conn, company_id)
    res = outcomes.close_due(conn, company_id)
    res["started"] = started
    if started and not res.get("closed"):
        res["summary"] = f"{started} accepted experiment{'s' if started > 1 else ''} started."
    return res


def _consume_result(res: dict) -> dict:
    return {"actions_proposed": res.get("actions_proposed", 0), "detail": res}


def by_key() -> dict[str, Watcher]:
    return {w.key: w for w in all_watchers()}
