"""
The verification worksheet and the proposal of the fifty.

An hour with Shourya is only enough if every case is already on the page, and
the proposal is only trustworthy if it cannot be gamed into "the fifty that
pass today". Both are pure functions of a report dict, so these tests feed
them fakes — nothing here touches a database.
"""
import copy
from collections import Counter

from vinayak.eval import frozen as F
from vinayak.eval.cases import BOTH, CASES
from vinayak.eval.worksheet import (order_for_review, propose_freeze, render_proposal,
                                    render_worksheet)

CASE_SET = [
    {"id": "receivables", "q": "Who owes me money and who is overdue?",
     "expect_intent": "receivables", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "ar_total", "oracle": "ar_outstanding"}]},
    {"id": "ca_gst", "q": "What is our GST liability for this month?",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True, "must_not_say": ["you owe"]},
    {"id": "inventory", "q": "How much stock value am I holding?",
     "expect_intent": "inventory", "expect_bucket": {"CERTAIN"},
     "verified": {"by": "shourya", "on": "2027-01-10", "note": "figure matches Tally"}},
]


def _row(cid, company, passed=True, **kw):
    r = {"id": cid, "company": company, "question": "", "intent": "receivables",
         "confidence": "CERTAIN", "answer": "You are owed ₹1.2Cr.\nMost of it is late.",
         "evidence": [{"id": "ar_total", "label": "Total outstanding | all",
                       "value": 12000000.0, "display": "₹1.20Cr"}],
         "fact_checks": [], "is_refusal": False, "must_not_violations": [],
         "checks": {"intent_ok": True, "bucket_ok": True, "refusal_ok": True,
                    "must_not_say_ok": True, "no_unsupported": True, "facts_ok": passed},
         "passed": passed}
    r.update(kw)
    return r


def _report():
    return {
        "metrics": {"set": "candidates", "passed": 5, "cases_run": 6,
                    "citation_compliance": 1.0, "factual_accuracy": 0.5, "facts_graded": 2},
        "results": [
            _row("receivables", "kbrushes"),
            _row("receivables", "protegere", passed=False,
                 fact_checks=[{"evidence": "ar_total", "oracle": "ar_outstanding",
                               "truth": 11000000.0, "got": 12000000.0, "ok": False,
                               "why": "stale snapshot"}]),
            _row("ca_gst", "kbrushes", intent="not_in_data", confidence="UNCERTAIN",
                 answer="GST isn't in the data I hold.", evidence=[], is_refusal=True),
            _row("ca_gst", "protegere", intent="not_in_data", confidence="UNCERTAIN",
                 answer="GST isn't in the data I hold.", evidence=[], is_refusal=True),
            _row("inventory", "kbrushes", intent="inventory"),
            _row("inventory", "protegere", intent="inventory"),
        ],
    }


# ── the worksheet ──────────────────────────────────────────────────────────
def test_failing_cases_come_first_then_refusals_then_the_rest():
    ordered = order_for_review(CASE_SET, _report()["results"])
    assert [c["id"] for c in ordered] == ["receivables", "ca_gst", "inventory"]


def test_a_case_that_did_not_run_is_left_off_the_worksheet():
    results = [r for r in _report()["results"] if r["id"] != "inventory"]
    assert "inventory" not in [c["id"] for c in order_for_review(CASE_SET, results)]


def test_every_case_carries_its_question_answer_evidence_truth_and_checkboxes():
    text = render_worksheet(_report(), CASE_SET, generated_on="2027-01-08")
    for case in CASE_SET:
        assert case["q"] in text
    assert "> You are owed ₹1.2Cr." in text
    assert "> Most of it is late." in text             # multi-line answers stay quoted
    assert "| `ar_total` | Total outstanding \\| all | 12,000,000 | ₹1.20Cr |" in text
    assert "11,000,000" in text and "stale snapshot" in text   # the oracle's truth
    assert "facts ✗" in text
    assert text.count("- [ ] Correct?") == 3
    assert text.count("- [ ] Phrasing real?") == 3
    assert text.count("- [ ] Keep in the 50?") == 3
    assert text.count("Notes: ___") == 3


def test_the_worksheet_says_which_cases_are_already_verified_and_what_is_expected():
    text = render_worksheet(_report(), CASE_SET, generated_on="2027-01-08")
    assert "verified by shourya on 2027-01-10 — figure matches Tally" in text
    assert text.count("not yet verified") == 2
    assert "**must refuse**" in text and "must not say “you owe”" in text
    assert "3 cases (1 failing, 1 refusals, 1 already verified)" in text


def test_the_worksheet_headings_follow_the_review_order():
    text = render_worksheet(_report(), CASE_SET, generated_on="2027-01-08")
    assert (text.index("## 1. `receivables` — FAILING")
            < text.index("## 2. `ca_gst` — refusal")
            < text.index("## 3. `inventory` — passing"))


# ── proposing the fifty ────────────────────────────────────────────────────
def _all_pass(cases):
    return [_row(c["id"], co) for c in cases for co in c.get("companies", BOTH)]


def test_the_proposal_is_fifty_cases_that_all_run_on_every_workspace():
    p = propose_freeze(CASES, _all_pass(CASES))
    assert len(p["ids"]) == 50 and p["short_by"] == 0
    assert len(set(p["ids"])) == 50
    by_id = {c["id"]: c for c in CASES}
    assert all(F.applies_everywhere(by_id[i]) for i in p["ids"])
    assert "creditworthy" in p["ineligible"] and "stretch_with_fact" in p["ineligible"]


def test_refusals_are_included_in_proportion():
    """15 of the 58 eligible cases are refusals → 13 of 50."""
    p = propose_freeze(CASES, _all_pass(CASES))
    eligible = [c for c in CASES if F.applies_everywhere(c)]
    share = sum(1 for c in eligible if c.get("refusal")) / len(eligible)
    assert p["refusals"] == round(50 * share)


def test_verified_passing_cases_are_taken_before_anything_else():
    ok = {"by": "shourya", "on": "2027-01-10"}
    cases = [{"id": f"u{i}", "q": f"u{i}", "expect_intent": f"i{i}"} for i in range(4)] + \
            [{"id": f"v{i}", "q": f"v{i}", "expect_intent": f"i{i}", "verified": ok} for i in range(3)]
    results = _all_pass(cases)
    for r in results:
        if r["id"] == "v2":
            r["passed"] = False
    p = propose_freeze(cases, results, n=2)
    assert p["ids"] == ["v0", "v1"]
    assert propose_freeze(cases, results, n=3)["ids"] == ["v0", "v1", "v2"]


def test_a_verified_case_outranks_an_unverified_one_even_when_failing():
    cases = [
        {"id": "a", "q": "a", "expect_intent": "x"},
        {"id": "b", "q": "b", "expect_intent": "x",
         "verified": {"by": "shourya", "on": "2027-01-10"}},
    ]
    results = [_row("a", co) for co in BOTH] + [_row("b", co, passed=False) for co in BOTH]
    assert propose_freeze(cases, results, n=1)["ids"] == ["b"]


def test_a_passing_case_outranks_a_failing_one_at_the_same_verification():
    cases = [{"id": "a", "q": "a", "expect_intent": "x"},
             {"id": "b", "q": "b", "expect_intent": "y"}]
    results = [_row("a", co, passed=False) for co in BOTH] + [_row("b", co) for co in BOTH]
    assert propose_freeze(cases, results, n=1)["ids"] == ["b"]


def test_the_pick_is_balanced_across_intents():
    """Five ageing questions exist; with three intents on offer and three
    places, each intent gets one rather than ageing taking all three."""
    cases = ([{"id": f"age{i}", "q": f"age {i}", "expect_intent": "ar_ageing_over"} for i in range(5)]
             + [{"id": "inv", "q": "inv", "expect_intent": "inventory"},
                {"id": "grn", "q": "grn", "expect_intent": "grn_status"}])
    p = propose_freeze(cases, _all_pass(cases), n=3)
    assert Counter(p["by_intent"]) == Counter({"ar_ageing_over": 1, "inventory": 1, "grn_status": 1})


def test_intents_stay_balanced_on_the_real_set():
    p = propose_freeze(CASES, _all_pass(CASES))
    counts = Counter(p["by_intent"])
    counts.pop("not_in_data", None)          # the unrouted refusals share one name
    assert max(counts.values()) <= 5          # no single intent crowds the set


def test_failing_cases_are_not_excluded_only_deprioritised():
    """The criterion is 80%, not 100%; a set of only today's passes measures
    nothing but the choice of set."""
    results = [dict(r, passed=False) for r in _all_pass(CASES)]
    p = propose_freeze(CASES, results)
    assert len(p["ids"]) == 50
    assert len(p["failing"]) == 50


def test_a_case_marked_not_to_keep_is_never_proposed():
    cases = copy.deepcopy(CASES)
    cases[0]["verified"] = {"by": "shourya", "on": "2027-01-10", "keep": False}
    p = propose_freeze(cases, _all_pass(cases))
    assert cases[0]["id"] not in p["ids"]
    assert cases[0]["id"] in p["ineligible"]


def test_a_set_too_small_to_fill_says_how_short_it_is():
    p = propose_freeze(CASE_SET, _report()["results"])
    assert len(p["ids"]) == 3 and p["short_by"] == 47


def test_the_proposal_ends_with_the_freeze_command():
    p = propose_freeze(CASES, _all_pass(CASES))
    text = render_proposal(p, CASES)
    assert "python -m vinayak.eval.frozen " + " ".join(p["ids"]) + " --write" in text
    assert "verify these before freezing" in text     # nothing is verified yet
