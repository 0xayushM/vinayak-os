"""
Unit tests for AR aging bucket computation — the numbers behind the AR page
and every collections answer. days_overdue derives from due_date vs today;
buckets are 0-30 / 31-60 / 61-90 / 90+.
"""
from datetime import date, timedelta

from vinayak.pipelines.ar_aging import ARAgingRow


def _row(due: date) -> ARAgingRow:
    return ARAgingRow(
        company_name="ACME", document_number="INV-1",
        payment_date=due, balance_amount=1000.0, amount_owe=1000.0,
    )


def test_not_yet_due_is_zero_and_first_bucket():
    r = _row(date.today() + timedelta(days=10))
    assert r.days_overdue == 0
    assert r.aging_bucket == "0-30"


def test_bucket_boundaries():
    assert _row(date.today() - timedelta(days=30)).aging_bucket == "0-30"
    assert _row(date.today() - timedelta(days=31)).aging_bucket == "31-60"
    assert _row(date.today() - timedelta(days=60)).aging_bucket == "31-60"
    assert _row(date.today() - timedelta(days=61)).aging_bucket == "61-90"
    assert _row(date.today() - timedelta(days=90)).aging_bucket == "61-90"
    assert _row(date.today() - timedelta(days=91)).aging_bucket == "90+"


def test_days_overdue_counts_days():
    r = _row(date.today() - timedelta(days=45))
    assert r.days_overdue == 45
    assert r.aging_bucket == "31-60"


def test_epoch_millis_due_date_is_coerced():
    due = date.today() - timedelta(days=100)
    from datetime import datetime, timezone
    ms = int(datetime(due.year, due.month, due.day, tzinfo=timezone.utc).timestamp() * 1000)
    r = ARAgingRow(company_name="ACME", document_number="INV-2",
                   payment_date=ms, balance_amount=1.0, amount_owe=1.0)
    assert r.due_date == due
    assert r.aging_bucket == "90+"


def test_stable_row_id_is_deterministic():
    a = _row(date.today() - timedelta(days=5))
    b = _row(date.today() - timedelta(days=5))
    assert a.raw_id == b.raw_id  # same invoice+customer → same upsert key
