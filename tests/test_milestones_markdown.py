"""
The eval line of the milestone status block.

Criterion 3 is not "the latest eval run looked good". It is ≥ 80% factual and
100% citation on the frozen fifty, on the engine AND on the native path
production uses. The status line has to say that — and, until there is a
freeze, has to say exactly what it said before, rather than grow words for a
thing that does not exist yet. Fake status dicts; no database.
"""
from vinayak import milestones as MS
from vinayak.eval import frozen as F


def _status(**kw):
    s = {
        "company_id": "kbrushes",
        "dates": {"start": "2026-09-01", "month_3_demo": "2026-12-01",
                  "month_6_review": "2027-03-01", "month_8_latest": "2027-05-01",
                  "month_12_review": "2027-09-01", "month_24_review": "2028-09-01",
                  "days_to_month_6": 165},
        "tracked_user": "", "usage": None,
        "evals": [{"runner": "engine", "ran_at": "2026-09-16T10:00:00+00:00", "cases_run": 58,
                   "passed": 58, "citation_compliance": 1.0, "factual_accuracy": 1.0,
                   "ship_blocked": False}],
        "experiments": {"with_outcomes": 0, "logged": 6, "ai_suggested": 5,
                        "ai_suggested_acted_on": 0},
        "incidents": {"critical_60d": 0, "days_since_critical": None},
    }
    s.update(kw)
    return s


def _eval_line(md: str) -> str:
    return next(ln for ln in md.splitlines() if ln.startswith("| 50-question eval"))


BEFORE = ("| 50-question eval: ≥ 80% factual, 100% citation | 58 cases (freeze at 50) · "
          "citation 100% · factual 100% (runner `engine`, 2026-09-16) |")


def _freeze(**kw):
    f = {"frozen": False, "frozen_on": None, "size": 0, "hash": None, "problems": [],
         "candidates": 60, "verified": 0}
    f.update(kw)
    return f


def _frozen_run(runner, fa=0.9, citation=1.0, frozen_hash="h1", questions=50, when="2027-01-20"):
    return {"runner": runner, "ran_at": f"{when}T06:00:00+00:00", "company_id": None,
            "metrics": {"set": "frozen", "frozen_hash": frozen_hash, "questions": questions,
                        "cases_run": questions * 2, "factual_accuracy": fa,
                        "citation_compliance": citation}}


def test_a_status_without_freeze_fields_reads_exactly_as_before():
    assert _eval_line(MS.as_markdown(_status())) == BEFORE


def test_nothing_frozen_and_nothing_verified_reads_exactly_as_before():
    s = _status(eval_freeze=_freeze(), frozen_evals=[])
    assert _eval_line(MS.as_markdown(s)) == BEFORE


def test_verified_cases_are_counted_before_the_freeze():
    s = _status(eval_freeze=_freeze(verified=23), frozen_evals=[])
    assert _eval_line(MS.as_markdown(s)) == (
        BEFORE[:-2] + " · not frozen yet · 23 of 60 cases verified |")


def test_a_frozen_set_reports_the_criterion_per_runner():
    s = _status(eval_freeze=_freeze(frozen=True, frozen_on="2027-01-15", size=50, hash="h1",
                                    verified=52),
                frozen_evals=[_frozen_run("engine", fa=0.92), _frozen_run("native", fa=0.74)])
    line = _eval_line(MS.as_markdown(s))
    assert "frozen at 50 on 2027-01-15 (hash `h1`)" in line
    assert "52 of 60 cases verified" in line
    assert "`engine` met (factual 92%, citation 100%, 2027-01-20)" in line
    assert "`native` NOT met (factual 74%, citation 100%, 2027-01-20)" in line


def test_a_runner_with_no_frozen_run_says_so():
    s = _status(eval_freeze=_freeze(frozen=True, frozen_on="2027-01-15", size=50, hash="h1",
                                    verified=50),
                frozen_evals=[_frozen_run("engine")])
    line = _eval_line(MS.as_markdown(s))
    assert "`engine` met" in line
    assert "`native` no frozen run recorded" in line


def test_a_run_on_an_earlier_freeze_is_not_counted():
    s = _status(eval_freeze=_freeze(frozen=True, frozen_on="2027-01-15", size=50, hash="h2",
                                    verified=50),
                frozen_evals=[_frozen_run("engine", frozen_hash="h1"),
                              _frozen_run("native", frozen_hash="h2")])
    line = _eval_line(MS.as_markdown(s))
    assert "`engine` last frozen run (2027-01-20) was on an earlier freeze" in line
    assert "`native` met" in line


def test_less_than_full_citation_is_not_met_even_with_high_factual_accuracy():
    s = _status(eval_freeze=_freeze(frozen=True, frozen_on="2027-01-15", size=50, hash="h1",
                                    verified=50),
                frozen_evals=[_frozen_run("engine", fa=1.0, citation=0.98)])
    assert "`engine` NOT met" in _eval_line(MS.as_markdown(s))


def test_a_drifted_freeze_is_flagged_on_the_line():
    s = _status(eval_freeze=_freeze(frozen=True, frozen_on="2027-01-15", size=50, hash="h1",
                                    verified=50, problems=["ca_gst: edited since the freeze"]),
                frozen_evals=[])
    assert "**freeze drifted: 1 problem(s)**" in _eval_line(MS.as_markdown(s))


def test_the_freeze_status_of_the_shipped_code_is_computed_without_a_database():
    f = MS.freeze_status()
    assert f["frozen"] is bool(F.FROZEN)
    assert f["candidates"] >= 50
    assert f["problems"] == []
