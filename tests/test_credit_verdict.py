"""
Unit tests for the deterministic credit gate (credit_verdict) — the non-AI half
of the Accounts → Sales synapse. Fixed thresholds, so the verdict must be exactly
reproducible: hold only when terms are stretched AND the customer is over-exposed
or concentrated; watch on any single flag; ok otherwise.
"""
from vinayak.schema.queries import (
    credit_verdict, CREDIT_STRETCH_DAYS,
    CREDIT_HIGH_EXPOSURE_SHARE, CREDIT_CONCENTRATION_SHARE,
)


def test_clean_customer_is_ok():
    v = credit_verdict(oldest_days_overdue=0, exposure_share_pct=1.0, revenue_share_pct=1.0)
    assert v["verdict"] == "ok"
    assert v["flags"] == []


def test_overdue_but_small_is_watch():
    v = credit_verdict(oldest_days_overdue=20, exposure_share_pct=1.0, revenue_share_pct=1.0)
    assert v["verdict"] == "watch"
    assert v["flags"] == ["overdue"]


def test_stretched_and_high_exposure_is_hold():
    v = credit_verdict(oldest_days_overdue=CREDIT_STRETCH_DAYS,
                       exposure_share_pct=CREDIT_HIGH_EXPOSURE_SHARE,
                       revenue_share_pct=1.0)
    assert v["verdict"] == "hold"
    assert "stretched" in v["flags"] and "high_exposure" in v["flags"]


def test_stretched_and_concentrated_is_hold():
    v = credit_verdict(oldest_days_overdue=120, exposure_share_pct=1.0,
                       revenue_share_pct=CREDIT_CONCENTRATION_SHARE)
    assert v["verdict"] == "hold"
    assert "concentration" in v["flags"]


def test_stretched_alone_is_watch_not_hold():
    # stretched terms but small exposure and low concentration → watch, not hold
    v = credit_verdict(oldest_days_overdue=90, exposure_share_pct=2.0, revenue_share_pct=2.0)
    assert v["verdict"] == "watch"
    assert "stretched" in v["flags"]


def test_high_exposure_but_current_is_watch():
    # over-exposed but not overdue → watch (a single flag), never hold
    v = credit_verdict(oldest_days_overdue=0, exposure_share_pct=40.0, revenue_share_pct=1.0)
    assert v["verdict"] == "watch"
    assert v["flags"] == ["high_exposure"]
