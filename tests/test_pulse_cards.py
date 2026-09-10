"""
The card contract: every Pulse card names a delta, a cause or a decision, and
never claims more certainty than its data supports. These run without a
database — the query functions are exercised against real Postgres separately.
"""
import pytest

from vinayak.schema import pulse_cards as C
from vinayak.schema.pulse import CERTAIN, PROBABLE, UNCERTAIN

REQUIRED = {"key", "title", "headline", "change", "why", "items", "action",
            "confidence", "severity", "stale", "last_synced_at"}


def _drift(**over):
    d = {"window_days": 30, "history_building": False, "history_days": 45,
         "bad_now": 1_700_000.0, "bad_then": 620_000.0, "drift": 1_080_000.0,
         "drift_pct": 8.1, "total_outstanding": 2_470_000.0,
         "movers": [{"customer_name": "DEV COLOUR", "delta": 500_000.0, "now": 1_120_000.0},
                    {"customer_name": "SHREE SHYAM", "delta": 490_000.0, "now": 490_000.0}],
         "stale": False, "last_synced_at": "2026-09-10T09:00:00+00:00"}
    d.update(over)
    return d


def test_every_card_satisfies_the_contract():
    cards = [
        C.card_aging_drift(_drift()),
        C.card_payment_behaviour({"items": [], "worsened": [], "basis": "current_book",
                                  "payment_history_days": 0, "avg_days_to_pay": None,
                                  "stale": False, "last_synced_at": None}),
        C.card_cash_30d({"horizon_days": 30, "inflow_due": 470000.0, "overdue_total": 2000000.0,
                         "inflow_expected_from_overdue": 1000000.0, "collection_factor": 0.5,
                         "inflow": 1470000.0, "outflow": 770000.0, "open_po_count": 3,
                         "net": 700000.0, "stale": False, "last_synced_at": None}),
        C.card_week_delta({"no_data": True, "stale": False, "last_synced_at": None}),
        C.card_reorder_radar({"items": [], "flagged_count": 0, "value_at_stake": 0,
                              "anchor_date": "2026-09-03", "stale": False, "last_synced_at": None}),
        C.card_concentration({"window_days": 90, "top1_pct": 45.5, "top3_pct": 84.5,
                              "top1_pct_prev": 44.1, "top3_pct_prev": 81.2, "top1_change": 1.4,
                              "top3_change": 3.3, "top_customer": "DEV COLOUR",
                              "revenue_window": 1.0, "revenue_prev": 1.0,
                              "stale": False, "last_synced_at": None}),
        C.card_trapped_capital({"dead_value": 96629.0, "dead_count": 2, "dead_value_before": 96629.0,
                                "dead_count_before": 2, "delta": 0.0, "delta_pct": 0.0,
                                "since_days": 90, "compare_days": 30,
                                "stale": False, "last_synced_at": None}),
        C.card_anomalies({"items": [], "count": 0}),
        C.card_working_capital({"inventory": 1.0, "receivables": 2.0, "open_commitments": 3.0,
                                "locked": 3.0, "net": 0.0, "has_true_ap": False,
                                "stale": False, "last_synced_at": None}),
    ]
    for c in cards:
        assert REQUIRED <= set(c), f"{c['key']} is missing {REQUIRED - set(c)}"
        assert c["why"], f"{c['key']} has no sentence explaining itself"
        assert c["confidence"] in (CERTAIN, PROBABLE, UNCERTAIN)
        assert 0 <= c["severity"] <= 100
        assert set(c["headline"]) == {"value", "display"}
        if c["change"] is not None:
            assert set(c["change"]) == {"value", "display", "direction", "label"}
            assert c["change"]["direction"] in ("good", "bad", "flat")


def test_aging_drift_names_the_customers_who_moved():
    c = C.card_aging_drift(_drift())
    assert "DEV COLOUR" in c["why"] and "SHREE SHYAM" in c["why"]
    assert c["action"]["kind"] == "draft_chase"
    assert c["change"]["direction"] == "bad"        # money sliding later is bad
    assert c["severity"] > 60                        # 8.1% of the book moved — urgent


def test_history_still_building_refuses_to_show_a_number():
    c = C.card_aging_drift(_drift(history_building=True, history_days=3))
    assert c["headline"]["display"] == "—"
    assert c["confidence"] == UNCERTAIN
    assert "history" in c["why"].lower()
    assert c["severity"] < 10                        # must not shout while it has nothing to say


def test_a_proxy_is_labelled_probable_not_certain():
    """Payment behaviour ranked on the current book is an inference; the cash
    view assumes half the overdue lands. Neither may claim CERTAIN."""
    behaviour = C.card_payment_behaviour({
        "items": [{"customer_name": "SHREE SHYAM", "outstanding": 490000.0, "overdue": 490000.0,
                   "oldest_days_overdue": 58, "weighted_days_late": 58.0, "score": 0.7}],
        "worsened": [], "basis": "current_book", "payment_history_days": 45,
        "avg_days_to_pay": None, "stale": False, "last_synced_at": None})
    assert behaviour["confidence"] == PROBABLE
    cash = C.card_cash_30d({"horizon_days": 30, "inflow_due": 1.0, "overdue_total": 2.0,
                            "inflow_expected_from_overdue": 1.0, "collection_factor": 0.5,
                            "inflow": 2.0, "outflow": 1.0, "open_po_count": 1, "net": 1.0,
                            "stale": False, "last_synced_at": None})
    assert cash["confidence"] == PROBABLE


def test_real_days_to_pay_is_certain_and_leads_with_the_slowdown():
    c = C.card_payment_behaviour({
        "items": [], "basis": "days_to_pay", "payment_history_days": 120, "avg_days_to_pay": 47.0,
        "worsened": [{"customer_name": "DEV COLOUR", "days_slower": 18.4,
                      "avg_now": 63.0, "avg_before": 44.6}],
        "stale": False, "last_synced_at": None})
    assert c["confidence"] == CERTAIN
    assert "DEV COLOUR" in c["why"] and "18.4" in c["why"]


def test_a_cash_shortfall_outranks_everything_quiet():
    short = C.card_cash_30d({"horizon_days": 30, "inflow_due": 100.0, "overdue_total": 0.0,
                             "inflow_expected_from_overdue": 0.0, "collection_factor": 0.5,
                             "inflow": 100.0, "outflow": 900.0, "open_po_count": 4,
                             "net": -800.0, "stale": False, "last_synced_at": None})
    calm = C.card_concentration({"window_days": 90, "top1_pct": 20.0, "top3_pct": 40.0,
                                 "top1_pct_prev": 20.0, "top3_pct_prev": 40.0, "top1_change": 0.0,
                                 "top3_change": 0.0, "top_customer": "X", "revenue_window": 1.0,
                                 "revenue_prev": 1.0, "stale": False, "last_synced_at": None})
    assert short["severity"] > calm["severity"]
    assert short["change"]["direction"] == "bad"


def test_unchanged_values_read_as_unchanged_not_as_zero():
    c = C.card_trapped_capital({"dead_value": 96629.0, "dead_count": 2, "dead_value_before": 96629.0,
                                "dead_count_before": 2, "delta": 0.0, "delta_pct": 0.0,
                                "since_days": 90, "compare_days": 30,
                                "stale": False, "last_synced_at": None})
    assert "unchanged" in c["why"]
    assert c["change"] is None            # no arrow when nothing moved
    assert "SKUs" in c["why"]
    one = C.card_trapped_capital({"dead_value": 1.0, "dead_count": 1, "dead_value_before": 0.0,
                                  "dead_count_before": 0, "delta": 1.0, "delta_pct": 0.0,
                                  "since_days": 90, "compare_days": 30,
                                  "stale": False, "last_synced_at": None})
    assert "1 SKU " in one["why"]         # singular


@pytest.mark.parametrize("role", list(C.ROLE_ORDER))
def test_every_role_orders_every_card(role):
    assert set(C.ROLE_ORDER[role]) == {k for k, _q, _c in C._BUILDERS}, \
        f"{role}'s layout must place every card exactly once"
    assert len(C.ROLE_ORDER[role]) == len(set(C.ROLE_ORDER[role]))
