"""
The Milestone-1 usage rule, stated in vinayak/usage.py: a Monday–Sunday week
qualifies at ≥ 4 active days; a run is consecutive qualifying complete weeks;
60 days is met at ≥ 9 such weeks (63 days). The partial current week never
breaks a run.
"""
from datetime import date, timedelta

from vinayak.usage import weekly_summary


def _days(start: date, weeks: int, per_week: int) -> list[date]:
    out = []
    for w in range(weeks):
        monday = start + timedelta(days=7 * w)
        out += [monday + timedelta(days=i) for i in range(per_week)]
    return out


MON = date(2026, 11, 2)   # a Monday


def test_nine_qualifying_weeks_meet_60_days():
    days = _days(MON, 9, 4)
    s = weekly_summary(days, today=MON + timedelta(days=9 * 7 + 2))
    assert s["best_run_weeks"] == 9 and s["best_run_days"] == 63
    assert s["meets_60_days"] is True


def test_eight_weeks_do_not():
    s = weekly_summary(_days(MON, 8, 5), today=MON + timedelta(days=8 * 7 + 1))
    assert s["best_run_days"] == 56 and s["meets_60_days"] is False


def test_a_three_day_week_breaks_the_run():
    days = _days(MON, 5, 4) + _days(MON + timedelta(days=35), 1, 3) + _days(MON + timedelta(days=42), 5, 4)
    s = weekly_summary(days, today=MON + timedelta(days=11 * 7 + 1))
    assert s["best_run_weeks"] == 5
    assert s["current_run_weeks"] == 5


def test_partial_current_week_does_not_break_the_run():
    days = _days(MON, 4, 4) + [MON + timedelta(days=28)]   # Monday of the current week only
    s = weekly_summary(days, today=MON + timedelta(days=29))
    assert s["current_run_weeks"] == 4
    assert s["current_week"]["partial"] is True and s["current_week"]["active_days"] == 1


def test_empty():
    s = weekly_summary([], today=MON)
    assert s["meets_60_days"] is False and s["best_run_days"] == 0
