"""
The rules the brain runs on, tested where they are pure.

Three things are worth pinning down without a database, because each one is a
decision rather than a query:

  • which collections rung an invoice has reached — the ladder is the reason
    a customer is not chased with the same letter every week;
  • how an experiment's outcome is decided from two readings — including that
    'inconclusive' is a real answer and not a bug;
  • what the weekly watcher chooses to suggest, and how it words it.

The SQL underneath is verified separately against a real Postgres with a
seeded business; these are the judgements.
"""
from datetime import date

import pytest

from vinayak.brain.detectors import RUNGS, _rung_for
from vinayak.brain.outcomes import verdict
from vinayak.brain.strategy import build_suggestions
from vinayak.brain.registry import all_watchers, by_key


# ── the collections ladder ────────────────────────────────────────────────
@pytest.mark.parametrize("days, expected", [
    (0, None), (3, None), (6, None),
    (7, 7), (12, 7), (29, 7),
    (30, 30), (59, 30),
    (60, 60), (89, 60),
    (90, 90), (400, 90),
])
def test_rung_is_the_highest_line_crossed(days, expected):
    assert _rung_for(days) == expected


def test_rungs_are_ordered_and_unique():
    assert list(RUNGS) == sorted(set(RUNGS))


# ── how an experiment is judged ───────────────────────────────────────────
def test_lower_is_better_metric_that_falls_is_positive():
    out, why = verdict(1_000_000, 800_000, lower_is_better=True)
    assert out == "positive" and "20%" in why


def test_lower_is_better_metric_that_rises_is_negative():
    out, _ = verdict(1_000_000, 1_200_000, lower_is_better=True)
    assert out == "negative"


def test_higher_is_better_flips_the_direction():
    assert verdict(100, 130, lower_is_better=False)[0] == "positive"
    assert verdict(100, 80, lower_is_better=False)[0] == "negative"


def test_a_small_move_is_noise_not_a_result():
    assert verdict(1_000_000, 980_000, lower_is_better=True)[0] == "inconclusive"


def test_hitting_the_target_is_positive_even_on_a_small_move():
    out, why = verdict(100, 96, lower_is_better=True, target=96)
    assert out == "positive" and "target" in why


def test_an_unreadable_metric_is_inconclusive_never_zero():
    assert verdict(100, None, lower_is_better=True)[0] == "inconclusive"
    assert verdict(None, 100, lower_is_better=True)[0] == "inconclusive"


def test_a_zero_baseline_cannot_be_improved_on():
    out, why = verdict(0, 0, lower_is_better=True)
    assert out == "inconclusive" and "zero" in why


# ── what the weekly watcher suggests ──────────────────────────────────────
TODAY = date(2026, 9, 10)


def test_nothing_to_suggest_from_an_empty_pulse():
    assert build_suggestions({}, TODAY) == []


def test_drift_below_the_floor_is_not_worth_a_suggestion():
    pulse = {"aging_drift": {"drift": 10_000, "history_building": False, "movers": []}}
    assert build_suggestions(pulse, TODAY) == []


def test_drift_suggestion_names_the_figure_and_the_movers():
    pulse = {"aging_drift": {"drift": 550_000, "history_building": False, "window_days": 30,
                             "bad_now": 2_100_000,
                             "movers": [{"customer_name": "DEV COLOUR", "delta": 400_000}]}}
    s = build_suggestions(pulse, TODAY)[0]
    assert s["metric_key"] == "ar.bucket_60plus"
    assert "DEV COLOUR" in s["hypothesis"]
    assert s["window_days"] == 30
    assert s["dedupe_key"] == "drift60:2026W37"


def test_history_still_building_suggests_nothing_about_drift():
    pulse = {"aging_drift": {"drift": 900_000, "history_building": True, "movers": []}}
    assert build_suggestions(pulse, TODAY) == []


def test_one_quiet_regular_is_worded_in_the_singular():
    pulse = {"reorder": {"items": [{"customer_name": "SHREE SHYAM", "median_gap_days": 20,
                                    "days_since_last": 70, "avg_order_value": 85_000}],
                         "value_at_stake": 85_000}}
    s = build_suggestions(pulse, TODAY)[0]
    assert "SHREE SHYAM" in s["title"]
    assert " regulars" not in s["title"]
    assert s["metric_key"] == "customer.days_quiet"


def test_several_quiet_regulars_are_one_suggestion_not_several():
    items = [{"customer_name": f"C{i}", "median_gap_days": 20, "days_since_last": 50,
              "avg_order_value": 40_000} for i in range(4)]
    out = build_suggestions({"reorder": {"items": items, "value_at_stake": 160_000}}, TODAY)
    assert len(out) == 1
    assert "4 regulars" in out[0]["title"]
    assert "and 1 more" in out[0]["hypothesis"]


def test_a_vendor_price_rise_is_measured_on_that_vendor_and_item():
    pulse = {"anomalies": {"items": [{
        "kind": "vendor_price_jump", "severity": 45,
        "text": "SHAKTI raised PP Granules by 45%.",
        "entity_ref": "vendor:SHAKTI", "vendor_name": "SHAKTI",
        "item_code": "RM-1", "item_name": "PP Granules"}]}}
    s = build_suggestions(pulse, TODAY)[0]
    assert s["metric_key"] == "purchase.unit_price"
    assert s["entity_ref"] == "vendoritem:SHAKTI|RM-1"


def test_a_price_rise_with_no_item_code_is_skipped_rather_than_guessed():
    pulse = {"anomalies": {"items": [{"kind": "vendor_price_jump", "severity": 45,
                                      "text": "x", "entity_ref": "vendor:SHAKTI"}]}}
    assert build_suggestions(pulse, TODAY) == []


def test_concentration_only_fires_when_it_is_high_and_growing():
    high_and_rising = {"concentration": {"top1_pct": 55.0, "top1_change": 4.0,
                                         "top_customer": "DEV COLOUR", "window_days": 90}}
    high_but_falling = {"concentration": {"top1_pct": 55.0, "top1_change": -4.0,
                                          "top_customer": "DEV COLOUR", "window_days": 90}}
    assert len(build_suggestions(high_and_rising, TODAY)) == 1
    assert build_suggestions(high_but_falling, TODAY) == []


def test_every_suggestion_carries_what_is_needed_to_judge_it():
    pulse = {
        "aging_drift": {"drift": 550_000, "history_building": False, "movers": [], "bad_now": 1},
        "dead_stock": {"dead_value": 900_000, "dead_count": 12, "since_days": 90},
        "concentration": {"top1_pct": 55.0, "top1_change": 4.0, "top_customer": "X",
                          "window_days": 90},
    }
    out = build_suggestions(pulse, TODAY)
    assert len(out) == 3
    for s in out:
        assert s["title"] and s["hypothesis"]
        assert s["metric_key"] and s["window_days"] > 0 and s["dedupe_key"]


def test_dedupe_keys_are_unique_within_one_week():
    pulse = {
        "aging_drift": {"drift": 550_000, "history_building": False, "movers": [], "bad_now": 1},
        "dead_stock": {"dead_value": 900_000, "dead_count": 12, "since_days": 90},
        "concentration": {"top1_pct": 55.0, "top1_change": 4.0, "top_customer": "X",
                          "window_days": 90},
        "reorder": {"items": [{"customer_name": "A", "median_gap_days": 20,
                               "days_since_last": 60, "avg_order_value": 1}],
                    "value_at_stake": 1},
    }
    keys = [s["dedupe_key"] for s in build_suggestions(pulse, TODAY)]
    assert len(keys) == len(set(keys))


# ── the registry ──────────────────────────────────────────────────────────
def test_every_watcher_is_described_in_plain_words():
    for w in all_watchers():
        assert w.key and w.title and w.what_it_does
        assert w.interval_minutes >= 5
        assert w.what_it_does[0].isupper() and w.what_it_does.endswith(".")


def test_watcher_keys_are_unique():
    ws = all_watchers()
    assert len(by_key()) == len(ws)


def test_every_suggested_metric_exists():
    """A suggestion whose metric is not in the table can never be closed."""
    from vinayak.brain.metrics import METRICS
    pulse = {
        "aging_drift": {"drift": 550_000, "history_building": False, "movers": [], "bad_now": 1},
        "dead_stock": {"dead_value": 900_000, "dead_count": 12, "since_days": 90},
        "concentration": {"top1_pct": 55.0, "top1_change": 4.0, "top_customer": "X",
                          "window_days": 90},
        "reorder": {"items": [{"customer_name": "A", "median_gap_days": 20,
                               "days_since_last": 60, "avg_order_value": 1}],
                    "value_at_stake": 1},
        "payment_behaviour": {"worsened": [{"customer_name": "B", "days_slower": 15,
                                            "avg_now": 60, "avg_before": 45}]},
        "anomalies": {"items": [{"kind": "vendor_price_jump", "severity": 45, "text": "x",
                                 "vendor_name": "V", "item_code": "I", "item_name": "N",
                                 "entity_ref": "vendor:V"}]},
    }
    for s in build_suggestions(pulse, TODAY):
        assert s["metric_key"] in METRICS, s["metric_key"]


# ── the bus and the consumer must agree on the vocabulary ─────────────────
def test_every_event_type_a_detector_emits_has_a_handler():
    """A detector that raises events nobody handles is a silent leak: the
    events pile up, get expired by age, and nothing ever explains why."""
    import inspect
    from vinayak.brain import consumer, detectors

    emitted = set()
    for fn in detectors.DETECTORS.values():
        src = inspect.getsource(fn)
        for line in src.splitlines():
            if 'bus.emit(' in line or (line.strip().startswith('conn, company_id, "')):
                part = line.split('company_id, "')
                if len(part) > 1:
                    emitted.add(part[1].split('"')[0])
    assert emitted, "could not read the event types out of the detectors"
    assert emitted <= set(consumer.HANDLERS), emitted - set(consumer.HANDLERS)


def test_the_ladder_has_a_tone_for_every_rung():
    from vinayak.brain.consumer import TONE_FOR_RUNG
    assert set(TONE_FOR_RUNG) == set(RUNGS)
    assert TONE_FOR_RUNG[7] == "gentle" and TONE_FOR_RUNG[90] == "firm"
