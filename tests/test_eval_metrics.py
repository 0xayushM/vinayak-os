"""
Unit tests for the trust-harness gate logic (compute_metrics). These run in CI
WITHOUT a database, so the release-blocking rule itself is protected: a build
that would ship an uncited number, drop below 100% citation compliance, or utter
a forbidden phrase must be flagged here regardless of the eval DB.
"""
from vinayak.eval.harness import compute_metrics


def _result(computed=1, unsupported=0, must_not=(), is_refusal=False,
            intent_ok=True, bucket_ok=True, refusal_ok=True):
    checks = {
        "intent_ok": intent_ok, "bucket_ok": bucket_ok, "refusal_ok": refusal_ok,
        "must_not_say_ok": len(must_not) == 0, "no_unsupported": unsupported == 0,
    }
    return {
        "id": "c", "company": "x", "question": "q", "intent": "revenue",
        "confidence": "CERTAIN", "computed_claims": computed, "unsupported": unsupported,
        "must_not_violations": list(must_not), "is_refusal": is_refusal,
        "checks": checks, "passed": all(checks.values()),
    }


def test_clean_run_is_not_blocked_and_full_citation():
    m = compute_metrics([_result(), _result(), _result()])
    assert m["citation_compliance"] == 1.0
    assert m["unsupported_claim_rate"] == 0.0
    assert m["ship_blocked"] is False


def test_unsupported_claim_blocks_and_lowers_citation():
    # 1 of 4 computed claims can't trace to evidence → 75% citation, blocked.
    m = compute_metrics([_result(computed=3, unsupported=0),
                         _result(computed=1, unsupported=1)])
    assert m["unsupported_claim_rate"] == 0.25
    assert m["citation_compliance"] == 0.75
    assert m["ship_blocked"] is True


def test_forbidden_phrase_blocks_even_with_full_citation():
    m = compute_metrics([_result(must_not=("best-selling",))])
    assert m["citation_compliance"] == 1.0          # numbers all cited
    assert m["must_not_say_violations"] == 1
    assert m["ship_blocked"] is True                # but a banned phrase blocks


def test_correct_refusal_rate_over_refusal_cases_only():
    # two refusal cases, one answered wrongly (refusal_ok False)
    results = [_result(is_refusal=True, refusal_ok=True),
               _result(is_refusal=True, refusal_ok=False),
               _result(is_refusal=False)]
    m = compute_metrics(results)
    assert m["correct_refusal_rate"] == 0.5


def test_no_computed_claims_is_full_citation():
    m = compute_metrics([_result(computed=0, unsupported=0)])
    assert m["citation_compliance"] == 1.0
    assert m["ship_blocked"] is False
