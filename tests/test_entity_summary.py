"""
Unit tests for the entity_summary synthesis (the "reason once at ingest" job).
Covers the pure builder: aggregate rollup, fact surfacing, and the payment-terms
contradiction check that seeds the "re-ask a stale fact" loop.
"""
from vinayak.memory.entity_summary import build_customer_summary


def _agg(**over):
    base = dict(outstanding=250000.0, overdue=180000.0, oldest_days_overdue=95,
                revenue_total=2100000.0, invoice_count=42, last_activity="2026-06-30")
    base.update(over)
    return base


def _fact(key, value, status="active"):
    return {"claim_key": key, "claim_value": value, "status": status}


def test_summary_rolls_up_aggregates():
    s, md = build_customer_summary("customer:dev-colour", "Dev Colour", _agg(), [])
    assert s["outstanding"] == 250000.0
    assert s["invoice_count"] == 42
    assert s["last_activity"] == "2026-06-30"
    assert "Dev Colour" in md
    assert "₹2.10 L" in md or "₹21.00 L" in md   # revenue rendered in lakh/cr


def test_active_facts_surface_and_stale_ignored():
    facts = [_fact("payment_terms_days", 60), _fact("trusted", True, status="stale")]
    s, md = build_customer_summary("customer:x", "X", _agg(oldest_days_overdue=10), facts)
    keys = [f["key"] for f in s["active_facts"]]
    assert "payment_terms_days" in keys
    assert "trusted" not in keys          # stale fact excluded


def test_terms_contradiction_flags_when_invoices_run_late():
    facts = [_fact("payment_terms_days", 60)]
    s, _ = build_customer_summary("customer:x", "X", _agg(oldest_days_overdue=95), facts)
    assert len(s["contradictions"]) == 1
    assert "60d" in s["contradictions"][0]


def test_no_contradiction_within_grace():
    facts = [_fact("payment_terms_days", 60)]
    s, _ = build_customer_summary("customer:x", "X", _agg(oldest_days_overdue=70), facts)
    assert s["contradictions"] == []       # 70 <= 60 + 15 grace


def test_no_contradiction_without_terms_fact():
    s, _ = build_customer_summary("customer:x", "X", _agg(oldest_days_overdue=200), [])
    assert s["contradictions"] == []
