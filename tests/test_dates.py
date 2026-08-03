"""Unit tests for natural-language period parsing used by the Ask engine."""
from datetime import date

from vinayak.reasoning.dates import parse_period

TODAY = date(2026, 7, 7)  # fixed anchor so tests never drift


def test_today():
    p = parse_period("how much did I sell today", TODAY)
    assert p and p["start"] == p["end"] == "2026-07-07"


def test_yesterday():
    p = parse_period("sales yesterday", TODAY)
    assert p and p["start"] == p["end"] == "2026-07-06"


def test_this_month():
    p = parse_period("revenue this month", TODAY)
    assert p and p["start"] == "2026-07-01" and p["end"] == "2026-07-07"


def test_no_period_returns_none():
    assert parse_period("who are my top customers", TODAY) is None


def test_month_name_range():
    p = parse_period("difference between sales of every month from april to june", TODAY)
    assert p and p["start"] == "2026-04-01" and p["end"] == "2026-06-30"


def test_month_name_range_with_year():
    p = parse_period("sales between january and march 2026", TODAY)
    assert p and p["start"] == "2026-01-01" and p["end"] == "2026-03-31"


def test_month_range_future_months_resolve_to_past():
    # In July 2026, "from october to december" must mean 2025, not the future.
    p = parse_period("sales from october to december", TODAY)
    assert p and p["start"] == "2025-10-01" and p["end"] == "2025-12-31"


def test_month_range_spanning_year_boundary():
    p = parse_period("revenue from november to february", TODAY)
    assert p and p["start"] == "2025-11-01" and p["end"] == "2026-02-28"
