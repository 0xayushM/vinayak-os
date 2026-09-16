"""
The credit synapse — what Accounts knows, and whether Sales should be told.

`assess` is the whole judgement, and it is pure so the thresholds can be
argued with here rather than in front of a customer whose order got held.
"""
import pytest

from vinayak.flags import (
    EXPOSURE_SHARE_PCT, HOLD, VERY_OLD_DAYS, WATCH, assess,
)


def _ok(**kw):
    base = dict(customer="Acme", outstanding=200_000, oldest_days=10,
                exposure_share_pct=5.0, rung=0, broken_promises=0)
    base.update(kw)
    return base


# ── nothing wrong ─────────────────────────────────────────────────────────
def test_a_customer_who_pays_is_not_flagged():
    assert assess(**_ok()) is None


def test_being_slightly_late_is_not_a_credit_event():
    assert assess(**_ok(oldest_days=20, rung=1)) is None


# ── what raises a hold ────────────────────────────────────────────────────
def test_two_broken_promises_is_a_hold_whatever_else_is_true():
    """The only signal where the customer said something and did not do it.
    It outranks every arithmetic one, and it says so in the reason."""
    v = assess(**_ok(oldest_days=5, broken_promises=2))
    assert v["level"] == HOLD
    assert "not paying" in v["reason"]


def test_one_broken_promise_needs_age_behind_it():
    assert assess(**_ok(oldest_days=10, broken_promises=1)) is None
    assert assess(**_ok(oldest_days=60, broken_promises=1))["level"] == HOLD


def test_the_top_of_the_collections_ladder_is_a_hold():
    v = assess(**_ok(oldest_days=95, rung=4))
    assert v["level"] == HOLD and "four reminders" in v["reason"]


def test_a_very_old_balance_is_a_hold_on_its_own():
    assert assess(**_ok(oldest_days=VERY_OLD_DAYS))["level"] == HOLD
    # Just under the line, with nothing else wrong, is not a credit event.
    assert assess(**_ok(oldest_days=VERY_OLD_DAYS - 1)) is None


# ── what raises a watch ───────────────────────────────────────────────────
def test_concentration_is_a_watch_not_a_hold():
    """Not late — concentrated. Holding a customer who pays on time because
    they are big would be an own goal."""
    v = assess(**_ok(oldest_days=0, exposure_share_pct=EXPOSURE_SHARE_PCT + 5))
    assert v["level"] == WATCH and "concentrated" in v["reason"]


def test_a_couple_of_reminders_and_real_age_is_a_watch():
    v = assess(**_ok(oldest_days=50, rung=2))
    assert v["level"] == WATCH


# ── the reason has to be usable ───────────────────────────────────────────
@pytest.mark.parametrize("case", [
    _ok(broken_promises=2),
    _ok(oldest_days=60, broken_promises=1),
    _ok(oldest_days=95, rung=4),
    _ok(oldest_days=200),
    _ok(oldest_days=0, exposure_share_pct=40),
    _ok(oldest_days=50, rung=2),
])
def test_every_flag_names_the_customer_and_reads_as_a_sentence(case):
    v = assess(**case)
    assert v is not None
    assert case["customer"] in v["reason"]
    assert v["reason"].endswith(".")
    assert v["evidence"]["oldest_days"] == case["oldest_days"]


def test_a_hold_always_outranks_a_watch_when_both_are_true():
    """Concentrated AND ancient must be a hold — the worse fact wins."""
    v = assess(**_ok(oldest_days=200, exposure_share_pct=60))
    assert v["level"] == HOLD
