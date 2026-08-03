"""
Unit tests for the reasoning engine's safety-critical pure functions:
the numeric guard, claim validation, confidence gates, INR formatting,
and the keyword intent router. These are the functions that keep the AI
from stating a number it didn't compute — they must never regress.
"""
from vinayak.reasoning.engine import (
    Answer, Claim, Evidence,
    inr, _norm_num, _num_tokens, _numbers_supported, _validate, _gates, classify,
)


# ── INR formatting ─────────────────────────────────────────────────────────────
def test_inr_none():
    assert inr(None) == "—"

def test_inr_scales():
    assert inr(500) == "₹500"
    assert inr(1_500) == "₹1.5K"
    assert inr(2_50_000) == "₹2.50L"
    assert inr(3_00_00_000) == "₹3.00Cr"

def test_inr_negative():
    assert inr(-2_50_000) == "₹-2.50L"  # abs() picks the scale; sign survives


# ── Numeric guard ──────────────────────────────────────────────────────────────
def test_norm_num_variants():
    assert _norm_num("₹2.50L") == _norm_num("2.50 lakh") == "2.50l"
    assert _norm_num("₹3.00Cr") == _norm_num("3.00 crores") == "3.00cr"

def test_num_tokens_extracts_money_only():
    toks = _num_tokens("We billed ₹2.50L across 37 invoices (12%).")
    assert "2.50l" in toks
    # plain counts and percentages are not money tokens
    assert not any(t.startswith("37") for t in toks)

def _answer_with_evidence(display: str) -> Answer:
    ev = [Evidence("e1", "Sales", 250000, display)]
    return Answer("q", "revenue", f"Sales were {display}.", "CERTAIN",
                  claims=[Claim(f"Sales were {display}.", "computed", ["e1"])],
                  evidence=ev)

def test_numbers_supported_allows_computed_figures():
    ans = _answer_with_evidence("₹2.50L")
    assert _numbers_supported("Your sales came to ₹2.50L this month.", ans)

def test_numbers_supported_blocks_invented_figures():
    ans = _answer_with_evidence("₹2.50L")
    assert not _numbers_supported("Your sales came to ₹9.99L this month.", ans)

def test_numbers_supported_ignores_prose_without_money():
    ans = _answer_with_evidence("₹2.50L")
    assert _numbers_supported("Sales look healthy and stable.", ans)


# ── Claim validation ───────────────────────────────────────────────────────────
def test_validate_downgrades_untraceable_computed_claim():
    ans = Answer("q", "revenue", "x", "CERTAIN",
                 claims=[Claim("made up", "computed", ["missing_id"])],
                 evidence=[Evidence("e1", "s", 1, "₹1")])
    out = _validate(ans)
    assert out.claims[0].type == "inference"
    assert out.claims[0].assumption  # reason recorded

def test_validate_keeps_traceable_computed_claim():
    ans = Answer("q", "revenue", "x", "CERTAIN",
                 claims=[Claim("real", "computed", ["e1"])],
                 evidence=[Evidence("e1", "s", 1, "₹1")])
    assert _validate(ans).claims[0].type == "computed"

def test_validate_downgrades_computed_claim_with_no_evidence_list():
    ans = Answer("q", "revenue", "x", "CERTAIN",
                 claims=[Claim("no citation", "computed", [])],
                 evidence=[Evidence("e1", "s", 1, "₹1")])
    assert _validate(ans).claims[0].type == "inference"


# ── Confidence gates ───────────────────────────────────────────────────────────
def test_gates_force_uncertain_when_only_unknowns():
    ans = Answer("q", "margin", "can't", "CERTAIN",  # handler lied: CERTAIN
                 claims=[Claim("unknown thing", "unknown")], evidence=[])
    out = _gates(ans)
    assert out.confidence == "UNCERTAIN"
    assert out.gates["data"] == "fail"

def test_gates_pass_with_evidence_and_computed():
    ans = Answer("q", "revenue", "ok", "CERTAIN",
                 claims=[Claim("real", "computed", ["e1"])],
                 evidence=[Evidence("e1", "s", 1, "₹1")])
    out = _gates(ans)
    assert out.confidence == "CERTAIN"
    assert out.gates == {"data": "pass", "rule": "pass", "confidence": "CERTAIN"}

def test_gates_fail_rule_for_unknown_intent():
    ans = Answer("q", "unknown", "?", "PROBABLE",
                 claims=[Claim("x", "computed", ["e1"])],
                 evidence=[Evidence("e1", "s", 1, "₹1")])
    out = _gates(ans)
    assert out.gates["rule"] == "fail"
    assert out.confidence == "UNCERTAIN"


# ── Intent router ──────────────────────────────────────────────────────────────
def test_classify_known_intents():
    assert classify("Who owes me money right now?") == "receivables"
    assert classify("give me an overview of my business") == "business_pulse"
    assert classify("what are my worst selling products?") == "least_skus"
    assert classify("who should I chase for payment first?") == "collections_priority"

def test_classify_unknown():
    assert classify("what's the weather in Mumbai?") == "unknown"


def test_classify_monthly_comparisons_route_to_trend():
    assert classify("give me the difference between sales of every month from april to june") == "revenue_trend"
    assert classify("show sales for each month this year") == "revenue_trend"
    assert classify("month wise sales please") == "revenue_trend"
