"""
Factual grading — the half of the eval that says whether a number was right.

Citation compliance asks "did the engine cite something?". Factual accuracy
asks "was the thing it cited true?", and until this existed the second question
had no answer, which made "≥ 80% factual accuracy" a criterion nobody could
measure. These tests cover the comparison rule and the aggregation; the
oracles themselves are SQL and are exercised against a real database.
"""
import pytest

from vinayak.eval import oracles
from vinayak.eval.cases import CASES
from vinayak.eval.harness import compute_metrics


# ── the comparison rule ───────────────────────────────────────────────────
def test_numbers_match_inside_the_tolerance():
    assert oracles.matches(1_000_000, 1_000_000)
    assert oracles.matches(1_000_000, 1_004_000)          # 0.4%
    assert not oracles.matches(1_000_000, 1_010_000)      # 1.0%


def test_zero_only_matches_zero():
    assert oracles.matches(0, 0)
    assert not oracles.matches(0, 1)


def test_a_missing_figure_never_counts_as_right():
    assert not oracles.matches(None, 5)
    assert not oracles.matches(5, None)
    assert not oracles.matches(None, None)


def test_names_match_loosely_but_not_wrongly():
    assert oracles.matches("DEV COLOUR AND COATINGS PVT LTD",
                           "DEV COLOUR AND COATINGS PVT LTD")
    # the engine often shows a longer label around the same name
    assert oracles.matches("SAIBABA HARDWARE", "Top customer (SAIBABA  HARDWARE)")
    assert not oracles.matches("DEV COLOUR", "Harris Brushes India Pvt Ltd")


def test_a_wildly_wrong_count_is_caught():
    """The bug this grading actually found: 392 reported where 22 was true."""
    assert not oracles.matches(22.0, 392.0)


# ── aggregation ───────────────────────────────────────────────────────────
def _result(graded, right, **kw):
    base = {"computed_claims": 0, "unsupported": 0, "must_not_violations": [],
            "facts_graded": graded, "facts_right": right, "is_refusal": False,
            "passed": graded == right,
            "checks": {"intent_ok": True, "bucket_ok": True, "refusal_ok": True,
                       "must_not_say_ok": True, "no_unsupported": True,
                       "facts_ok": graded == right}}
    base.update(kw)
    return base


def test_factual_accuracy_is_the_share_of_checked_figures_that_were_right():
    m = compute_metrics([_result(4, 4), _result(4, 2)])   # 6 right of 8 checked
    assert m["facts_graded"] == 8
    assert m["factual_accuracy"] == 0.75


def test_nothing_checkable_reports_none_not_a_perfect_score():
    """An ungraded metric that renders as 1.0 is worse than no metric at all —
    it reads as evidence the criterion is met."""
    m = compute_metrics([_result(0, 0), _result(0, 0)])
    assert m["factual_accuracy"] is None
    assert m["facts_graded"] == 0


def test_a_wrong_fact_does_not_block_the_ship_gate_on_its_own():
    """Citation compliance is the ship-blocker — stating an uncited number is
    a different class of fault from stating a cited number that is stale or
    miscounted. The second fails its case loudly and is fixed; it does not
    stop a release on its own."""
    m = compute_metrics([_result(2, 0)])
    assert m["factual_accuracy"] == 0.0
    assert m["ship_blocked"] is False


# ── the case set ──────────────────────────────────────────────────────────
def test_every_expected_value_names_a_real_oracle():
    for case in CASES:
        for want in case.get("expect_values", []):
            assert want["oracle"] in oracles.ORACLES, (case["id"], want["oracle"])
            assert want.get("field", "value") in ("value", "label", "display")


def test_enough_cases_are_factually_graded_to_mean_something():
    graded = [c for c in CASES if c.get("expect_values")]
    assert len(graded) >= 10, f"only {len(graded)} cases check a figure"


def test_refusal_cases_are_never_graded_on_facts():
    """A case that should refuse has no figures to be right about."""
    for case in CASES:
        if case.get("refusal"):
            assert not case.get("expect_values"), case["id"]
