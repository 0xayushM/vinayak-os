"""
The freeze — what makes "a fixed 50-question set" auditable rather than asserted.

Criterion 3 is judged on fifty frozen cases. These tests hold the two things
that make the freeze mean something: a frozen case cannot be quietly edited,
and the criterion's own pass rule cannot be met on anything but the frozen
fifty. No database — the manifest, the hashes and the rule are all pure.
"""
import copy

import pytest

from vinayak.eval import frozen as F
from vinayak.eval.cases import BOTH, CASES
from vinayak.eval.harness import cases_for, compute_metrics, parse_args, run_metadata


def _verified(case, keep=True):
    c = copy.deepcopy(case)
    c["verified"] = {"by": "shourya", "on": "2027-01-10", "note": "checked", "keep": keep}
    return c


def _candidate_set():
    """The real cases, every one marked verified — what the set looks like on
    the day of the freeze."""
    return [_verified(c) for c in CASES]


def _fifty(cases):
    return [c["id"] for c in cases if F.applies_everywhere(c)][:50]


# ── the manifest as shipped ────────────────────────────────────────────────
def test_the_shipped_manifest_is_empty_or_exactly_fifty():
    assert len(F.FROZEN) in (0, F.FROZEN_SIZE)


def test_the_shipped_freeze_is_intact():
    """If this fails, a frozen case was edited: regenerate the manifest on
    purpose, or undo the edit."""
    assert F.check_frozen() == []


def test_every_verification_record_in_the_case_set_is_well_formed():
    for case in CASES:
        assert F.verification_problems(case) == [], case["id"]


# ── building the freeze ────────────────────────────────────────────────────
def test_a_freeze_of_fifty_verified_cases_builds_and_checks_clean():
    cases = _candidate_set()
    manifest = F.build_manifest(_fifty(cases), cases)
    assert len(manifest) == 50
    assert F.check_frozen(manifest, cases) == []


@pytest.mark.parametrize("size", [49, 51])
def test_a_freeze_must_hold_exactly_fifty(size):
    cases = _candidate_set()
    ids = [c["id"] for c in cases if F.applies_everywhere(c)][:size]
    with pytest.raises(F.FreezeError, match="exactly 50"):
        F.build_manifest(ids, cases)


def test_a_manifest_that_is_not_fifty_is_reported():
    cases = _candidate_set()
    manifest = F.build_manifest(_fifty(cases), cases)
    manifest.pop(next(iter(manifest)))
    assert any("not 50" in p for p in F.check_frozen(manifest, cases))


def test_an_unverified_case_cannot_be_frozen():
    cases = _candidate_set()
    ids = _fifty(cases)
    victim = next(c for c in cases if c["id"] == ids[0])
    del victim["verified"]
    with pytest.raises(F.FreezeError, match="not verified"):
        F.build_manifest(ids, cases)


def test_a_case_verified_as_not_worth_keeping_cannot_be_frozen():
    cases = _candidate_set()
    ids = _fifty(cases)
    next(c for c in cases if c["id"] == ids[0])["verified"]["keep"] = False
    with pytest.raises(F.FreezeError, match="not worth keeping"):
        F.build_manifest(ids, cases)


def test_a_single_workspace_case_cannot_be_frozen():
    """creditworthy only runs on kbrushes, so freezing it would leave a
    protegere run grading 49 questions."""
    cases = _candidate_set()
    ids = _fifty(cases)[:49] + ["creditworthy"]
    with pytest.raises(F.FreezeError, match="every workspace"):
        F.build_manifest(ids, cases)


# ── detecting a silent edit ────────────────────────────────────────────────
def _frozen_then(edit):
    cases = _candidate_set()
    ids = _fifty(cases)
    manifest = F.build_manifest(ids, cases)
    target = next(c for c in cases if c["id"] == ids[0])
    edit(target)
    return F.check_frozen(manifest, cases), ids[0]


def test_rewording_a_frozen_question_is_detected():
    problems, cid = _frozen_then(lambda c: c.update(q=c["q"] + " roughly"))
    assert any(p.startswith(f"{cid}: edited since the freeze") for p in problems)


def test_loosening_a_frozen_expectation_is_detected():
    def loosen(c):
        c["expect_bucket"] = set(c["expect_bucket"]) | {"UNCERTAIN", "PROBABLE", "CERTAIN"}
    problems, cid = _frozen_then(loosen)
    assert any(p.startswith(f"{cid}: edited since the freeze") for p in problems)


def test_dropping_a_forbidden_phrase_or_an_oracle_is_detected():
    problems, cid = _frozen_then(lambda c: c.update(must_not_say=[], expect_values=[],
                                                    expect_intent="something_else"))
    assert any(p.startswith(f"{cid}: edited") for p in problems)


def test_recording_a_verification_note_is_not_an_edit():
    problems, _ = _frozen_then(lambda c: c["verified"].update(note="rechecked in Feb"))
    assert problems == []


def test_removing_a_frozen_case_is_detected():
    cases = _candidate_set()
    ids = _fifty(cases)
    manifest = F.build_manifest(ids, cases)
    remaining = [c for c in cases if c["id"] != ids[0]]
    assert any("no longer in the case set" in p for p in F.check_frozen(manifest, remaining))


def test_removing_a_frozen_cases_sign_off_is_detected():
    problems, cid = _frozen_then(lambda c: c.pop("verified"))
    assert any(p.startswith(f"{cid}: frozen but its verification") for p in problems)


def test_the_hash_ignores_set_order_and_explicit_defaults():
    a = {"id": "x", "q": "q?", "expect_bucket": {"CERTAIN", "PROBABLE"}}
    b = {"id": "x", "q": "q?", "expect_bucket": {"PROBABLE", "CERTAIN"},
         "refusal": False, "companies": list(reversed(BOTH))}
    assert F.case_hash(a) == F.case_hash(b)


# ── running the frozen set ─────────────────────────────────────────────────
def test_asking_for_the_frozen_set_before_a_freeze_says_so_plainly():
    with pytest.raises(F.FreezeError, match="has not been frozen yet"):
        cases_for(True, CASES, manifest={})


def test_a_drifted_freeze_cannot_be_run():
    cases = _candidate_set()
    manifest = F.build_manifest(_fifty(cases), cases)
    cases[0]["q"] = "something else entirely"
    with pytest.raises(F.FreezeError, match="drifted"):
        cases_for(True, cases, manifest)


def test_the_frozen_run_grades_exactly_the_frozen_cases():
    cases = _candidate_set()
    ids = _fifty(cases)
    manifest = F.build_manifest(ids, cases)
    assert [c["id"] for c in cases_for(True, cases, manifest)] == ids
    assert len(cases_for(False, cases, manifest)) == len(cases)


def test_the_harness_flags_parse():
    a = parse_args(["kbrushes", "--runner", "native", "--frozen", "--record"])
    assert (a.company, a.runner, a.frozen, a.record) == ("kbrushes", "native", True, True)
    b = parse_args([])
    assert (b.company, b.runner, b.frozen, b.record) == (None, None, False, False)


# ── what a run records, and the criterion ──────────────────────────────────
def _rows(ids, companies=BOTH, right=True):
    return [{"id": i, "company": co, "computed_claims": 1, "unsupported": 0,
             "must_not_violations": [], "is_refusal": False,
             "facts_graded": 1, "facts_right": 1 if right else 0, "passed": right,
             "checks": {"intent_ok": True, "bucket_ok": True, "refusal_ok": True,
                        "must_not_say_ok": True, "no_unsupported": True, "facts_ok": right}}
            for i in ids for co in companies]


def test_a_run_over_both_workspaces_counts_fifty_questions_not_a_hundred_rows():
    cases = _candidate_set()
    ids = _fifty(cases)
    manifest = F.build_manifest(ids, cases)
    run_cases = cases_for(True, cases, manifest)
    m = run_metadata(compute_metrics(_rows(ids)), run_cases, True, manifest)
    assert m["cases_run"] == 100
    assert m["questions"] == 50
    assert m["set"] == "frozen"
    assert m["frozen_hash"] == F.manifest_hash(manifest)
    assert m["cases_verified"] == 50
    assert m["criterion_met"] is True


def test_a_candidates_run_records_its_set_and_never_meets_the_criterion():
    cases = copy.deepcopy(CASES)
    cases[0]["verified"] = {"by": "shourya", "on": "2027-01-10"}
    m = run_metadata(compute_metrics(_rows([c["id"] for c in cases][:50])), cases, False, {})
    assert m["set"] == "candidates"
    assert m["frozen_hash"] is None
    assert m["cases_verified"] == 1
    assert m["criterion_met"] is False


def _metrics(**kw):
    base = {"set": "frozen", "frozen_hash": "abc", "questions": 50, "cases_run": 100,
            "factual_accuracy": 0.80, "citation_compliance": 1.0}
    base.update(kw)
    return base


def test_the_criterion_is_met_at_exactly_eighty_percent_and_full_citation():
    assert F.criterion_met(_metrics())
    assert F.criterion_met(_metrics(), frozen_hash="abc")


@pytest.mark.parametrize("change", [
    {"factual_accuracy": 0.799},
    {"factual_accuracy": None},
    {"citation_compliance": 0.9999},
    {"set": "candidates"},
    {"questions": 49},
    {"questions": 58},
])
def test_the_criterion_fails_on_any_single_shortfall(change):
    assert not F.criterion_met(_metrics(**change))


def test_a_score_on_an_earlier_freeze_does_not_meet_the_criterion():
    assert not F.criterion_met(_metrics(), frozen_hash="a-newer-freeze")


def test_older_metrics_without_a_question_count_fall_back_to_cases_run():
    m = _metrics(cases_run=50)
    del m["questions"]
    assert F.criterion_met(m)


# ── generating the manifest source ─────────────────────────────────────────
def test_the_generated_manifest_replaces_the_block_and_round_trips():
    cases = _candidate_set()
    manifest = F.build_manifest(_fifty(cases), cases)
    source = open(F.__file__, encoding="utf-8").read()
    new = F.replace_manifest(source, F.manifest_source(manifest, "2027-01-15"))
    ns: dict = {}
    block = new[new.index("# BEGIN MANIFEST"):new.index("# END MANIFEST")]
    exec(block, ns)
    assert ns["FROZEN"] == manifest
    assert ns["FROZEN_ON"] == "2027-01-15"
    # the rest of the module is untouched
    assert new.replace(block, "") == source.replace(
        source[source.index("# BEGIN MANIFEST"):source.index("# END MANIFEST")], "")
