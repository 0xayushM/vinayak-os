"""
Month-3 demo readiness — PLAN.md §4, read before the day rather than on it.

`assess` is the whole judgement. The rule these tests hold it to: nothing
unreadable or uncountable ever shows as met.
"""
from datetime import date

from vinayak.demo_readiness import MANUAL, MET, SHORT, as_markdown, assess, complete_weeks


def _week(n, qualifies=None, partial=False):
    return {"week_start": "2026-11-02", "active_days": n,
            "qualifies": n >= 4 if qualifies is None else qualifies, "partial": partial}


def _ready(**kw):
    f = {
        "tracked_user": "sandeep@example.com",
        "brief": {"delivered_working_days": 26, "expected_working_days": 26,
                  "every_working_day": True, "missed": []},
        "usage_weeks": [_week(5), _week(4), _week(6), _week(4)],
        "watchers_unattended": 4, "agent_proposals": 12, "actions_executed": 11,
        "chases_logged": 7, "active_flags": 3,
        "experiments": {"logged": 14, "with_outcomes": 6, "ai_suggested": 9,
                        "running": 4, "proposed": 2},
        "evals": [{"runner": "engine", "cases_run": 50, "citation_compliance": 1.0,
                   "ran_at": "2026-11-28T00:00:00"},
                  {"runner": "native", "cases_run": 50, "citation_compliance": 1.0,
                   "ran_at": "2026-11-28T00:00:00"}],
        "critical_30d": 0,
    }
    f.update(kw)
    return f


def _state(rows, key):
    return next(r for r in rows if r["key"] == key)["state"]


def test_a_ready_workspace_meets_every_countable_criterion():
    rows = assess(_ready())
    assert {r["state"] for r in rows if r["key"] not in ("pulse", "incidents")} == {MET}


def test_what_cannot_be_counted_is_never_reported_as_met():
    rows = assess(_ready())
    assert _state(rows, "pulse") == MANUAL
    assert _state(rows, "incidents") == MANUAL


def test_without_a_tracked_user_brief_and_usage_are_short_whatever_else_is_true():
    rows = assess(_ready(tracked_user=""))
    assert _state(rows, "brief") == SHORT
    assert _state(rows, "usage") == SHORT


def test_a_missing_delivery_log_is_short_not_met():
    assert _state(assess(_ready(brief=None)), "brief") == SHORT


def test_one_missed_working_day_is_short_and_says_which():
    b = {"delivered_working_days": 25, "expected_working_days": 26,
         "every_working_day": False, "missed": ["2026-11-17"]}
    r = next(r for r in assess(_ready(brief=b)) if r["key"] == "brief")
    assert r["state"] == SHORT and "2026-11-17" in r["where"]


def test_one_light_week_in_four_fails_usage():
    rows = assess(_ready(usage_weeks=[_week(5), _week(3), _week(6), _week(4)]))
    assert _state(rows, "usage") == SHORT


def test_three_weeks_of_history_is_not_four():
    assert _state(assess(_ready(usage_weeks=[_week(5)] * 3)), "usage") == SHORT


def test_watchers_that_propose_nothing_do_not_meet_the_brain_criterion():
    assert _state(assess(_ready(agent_proposals=0)), "brain") == SHORT


def test_nine_executed_actions_is_short():
    assert _state(assess(_ready(actions_executed=9)), "brain") == SHORT


def test_experiments_mostly_typed_in_by_hand_do_not_count():
    x = {"logged": 12, "with_outcomes": 6, "ai_suggested": 5}
    assert _state(assess(_ready(experiments=x)), "experiments") == SHORT


def test_experiments_need_outcomes_not_just_a_log():
    x = {"logged": 20, "with_outcomes": 4, "ai_suggested": 15}
    assert _state(assess(_ready(experiments=x)), "experiments") == SHORT


def test_an_eval_graded_only_on_the_engine_path_is_short():
    rows = assess(_ready(evals=_ready()["evals"][:1]))
    r = next(r for r in rows if r["key"] == "eval")
    assert r["state"] == SHORT and "native" in r["where"]


def test_an_eval_below_full_citation_is_short():
    evals = _ready()["evals"]
    evals[1] = {**evals[1], "citation_compliance": 0.98}
    assert _state(assess(_ready(evals=evals)), "eval") == SHORT


def test_a_critical_incident_makes_the_incident_line_short():
    assert _state(assess(_ready(critical_30d=1)), "incidents") == SHORT


def test_complete_weeks_ignores_the_week_in_progress():
    weekly = {"weeks": [_week(4), _week(5), _week(4), _week(6), _week(1, partial=True)]}
    got = complete_weeks(weekly)
    assert len(got) == 4 and not any(w["partial"] for w in got)


def test_the_markdown_counts_what_is_met_and_what_is_manual():
    md = as_markdown("kbrushes", assess(_ready()), today=date(2026, 11, 30))
    assert "7 of 9 met, 2 to check by hand" in md
