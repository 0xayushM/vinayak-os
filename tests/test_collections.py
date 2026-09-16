"""
The collections ladder — the rules that decide whether a customer hears from
us at all, and in what words.

Every one of these is a judgement somebody could reasonably disagree with,
which is exactly why they are pure functions with tests: an argument about
collections policy should happen here, not in a customer's inbox.
"""
from datetime import date, datetime, timedelta, timezone

import pytest

from vinayak.collections import (
    LADDER, MAX_RUNG, PROMISE_GRACE_DAYS,
    chase_priority, compose, decide, rung,
)

TODAY = date(2026, 9, 16)


def _state(**kw):
    base = {"rung": 0, "chases_sent": 0, "disputed": False}
    base.update(kw)
    return base


# ── who may be chased ─────────────────────────────────────────────────────
def test_a_disputed_balance_is_never_chased():
    """The argument is about the invoice. A reminder makes it worse."""
    d = decide(days_overdue=200, outstanding=5_000_000,
               state=_state(disputed=True), open_promise=None, today=TODAY)
    assert not d.allowed and "disputed" in d.reason


def test_a_promise_pauses_chasing_until_it_is_due():
    promise = {"promised_on": (TODAY + timedelta(days=5)).isoformat()}
    d = decide(days_overdue=90, outstanding=500_000, state=_state(),
               open_promise=promise, today=TODAY)
    assert not d.allowed and "promised" in d.reason


def test_a_promise_gets_grace_before_it_counts_as_broken():
    """Cheques clear late. Calling a promise broken on the morning after is
    the kind of accuracy that loses customers."""
    promise = {"promised_on": (TODAY - timedelta(days=PROMISE_GRACE_DAYS)).isoformat()}
    assert not decide(days_overdue=90, outstanding=500_000, state=_state(),
                      open_promise=promise, today=TODAY).allowed
    stale = {"promised_on": (TODAY - timedelta(days=PROMISE_GRACE_DAYS + 1)).isoformat()}
    assert decide(days_overdue=90, outstanding=500_000, state=_state(),
                  open_promise=stale, today=TODAY).allowed


def test_a_small_balance_is_not_worth_chasing():
    d = decide(days_overdue=200, outstanding=900, state=_state(),
               open_promise=None, today=TODAY)
    assert not d.allowed and "amount" in d.reason


def test_not_late_enough_yet():
    d = decide(days_overdue=3, outstanding=500_000, state=_state(),
               open_promise=None, today=TODAY)
    assert not d.allowed and d.rung == 0


def test_the_cooldown_stops_a_second_chase_too_soon():
    recent = datetime(2026, 9, 14, tzinfo=timezone.utc)
    d = decide(days_overdue=45, outstanding=500_000,
               state=_state(rung=1, chases_sent=1, last_chased_at=recent),
               open_promise=None, today=TODAY)
    assert not d.allowed and "waits" in d.reason


def test_the_cooldown_expires():
    old = datetime(2026, 8, 20, tzinfo=timezone.utc)
    d = decide(days_overdue=45, outstanding=500_000,
               state=_state(rung=1, chases_sent=1, last_chased_at=old),
               open_promise=None, today=TODAY)
    assert d.allowed and d.rung == 2


def test_a_manual_pause_is_respected():
    d = decide(days_overdue=90, outstanding=500_000,
               state=_state(paused_until=(TODAY + timedelta(days=3)).isoformat(),
                            pause_reason="MD is meeting them Thursday"),
               open_promise=None, today=TODAY)
    assert not d.allowed and "Thursday" in d.reason


def test_an_expired_pause_lets_chasing_resume():
    d = decide(days_overdue=90, outstanding=500_000,
               state=_state(paused_until=(TODAY - timedelta(days=1)).isoformat()),
               open_promise=None, today=TODAY)
    assert d.allowed


def test_dispute_beats_everything_else():
    """Order matters: a disputed account that is also enormous, ancient and
    un-paused must still not be chased."""
    d = decide(days_overdue=900, outstanding=50_000_000,
               state=_state(disputed=True), open_promise=None, today=TODAY)
    assert not d.allowed


# ── the wording ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_every_rung_names_the_amount_and_the_customer(level):
    subject, body = compose("Dev Colour", 600_000, 600_000, 120, level)
    assert "Dev Colour" in body
    assert "₹6.00L" in subject or "₹6.00L" in body


def test_each_rung_reads_differently():
    bodies = {compose("X", 100_000, 100_000, 60, lv)[1] for lv in (1, 2, 3, 4)}
    assert len(bodies) == 4


def test_only_the_last_two_rungs_threaten_a_hold():
    assert "hold" not in compose("X", 100_000, 100_000, 10, 1)[1].lower()
    assert "hold" not in compose("X", 100_000, 100_000, 40, 2)[1].lower()
    assert "hold" in compose("X", 100_000, 100_000, 70, 3)[1].lower()
    assert "hold" in compose("X", 100_000, 100_000, 100, 4)[1].lower()


def test_every_rung_leaves_a_way_back():
    """Even the hardest letter has to invite a conversation. A reminder whose
    only message is a threat collects nothing and ends a relationship."""
    for level in (1, 2, 3, 4):
        body = compose("X", 100_000, 100_000, 100, level)[1].lower()
        assert any(w in body for w in ("reply", "call us", "contact us", "update"))


def test_it_asks_for_the_overdue_figure_not_the_whole_balance():
    _s, body = compose("X", outstanding=1_000_000, overdue=250_000,
                       oldest_days=40, level=2)
    assert "₹2.50L" in body and "₹10.00L" not in body


def test_an_unknown_rung_is_clamped_rather_than_crashing():
    assert rung(0).level == 1
    assert rung(99).level == MAX_RUNG


# ── priority ──────────────────────────────────────────────────────────────
def test_priority_is_amount_times_lateness_not_amount_alone():
    """A big invoice that is barely late must rank below a smaller one that is
    ancient — chasing the biggest customer first is how a collections list
    wastes a morning."""
    big_and_fresh = chase_priority(5_000_000, 5)
    small_and_ancient = chase_priority(800_000, 200)
    assert small_and_ancient > big_and_fresh


def test_bad_behaviour_raises_priority_at_the_same_amount_and_age():
    assert chase_priority(1_000_000, 90, 0.8) > chase_priority(1_000_000, 90, 0.0)


def test_nothing_overdue_has_no_priority():
    assert chase_priority(1_000_000, 0) == 0.0
    assert chase_priority(0, 100) == 0.0


def test_lateness_is_capped_so_one_ancient_invoice_cannot_dominate():
    assert chase_priority(100_000, 400) == chase_priority(100_000, 365)


# ── the ladder's shape ────────────────────────────────────────────────────
def test_the_ladder_is_ordered_and_slows_as_it_climbs():
    assert [r.level for r in LADDER] == [1, 2, 3, 4]
    assert [r.from_days for r in LADDER] == sorted(r.from_days for r in LADDER)
    assert [r.cooldown_days for r in LADDER] == sorted(r.cooldown_days for r in LADDER)
