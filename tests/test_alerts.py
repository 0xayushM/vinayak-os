"""
Background failures must reach a person, once per condition, and the act of
alerting must never break the job being watched. The decisions are pure and
tested directly; the plumbing is tested against fake connections — nothing
here opens a database.
"""
from datetime import datetime, timedelta, timezone

import pytest

from vinayak import alerts as A

NOW = datetime(2026, 11, 12, 6, 0, tzinfo=timezone.utc)


# ── pure decisions ────────────────────────────────────────────────────────
def test_alert_recipients_are_parsed_from_a_comma_separated_env_value():
    assert A.recipients(" a@x.in, b@y.com ,,a@x.in; c@z.io") == ["a@x.in", "b@y.com", "c@z.io"]
    assert A.recipients("") == []
    assert A.recipients(None) == []
    assert A.recipients("not-an-address") == []


def test_a_bad_cooldown_value_falls_back_to_the_default_rather_than_to_zero():
    assert A.cooldown_hours(None) == A.DEFAULT_COOLDOWN_HOURS
    assert A.cooldown_hours("banana") == A.DEFAULT_COOLDOWN_HOURS
    assert A.cooldown_hours("0") == A.DEFAULT_COOLDOWN_HOURS
    assert A.cooldown_hours("-2") == A.DEFAULT_COOLDOWN_HOURS
    assert A.cooldown_hours("12") == 12.0


def test_a_condition_never_emailed_is_sent():
    assert A.should_send(None, NOW, 6) is True


def test_a_condition_emailed_within_the_cooldown_stays_quiet():
    assert A.should_send(NOW - timedelta(hours=5, minutes=59), NOW, 6) is False


def test_a_condition_that_persists_past_the_cooldown_is_sent_again():
    assert A.should_send(NOW - timedelta(hours=6), NOW, 6) is True


def test_a_watcher_counts_as_halted_from_the_failure_that_stops_its_scheduling():
    assert A.watcher_halted(2, 3) is False
    assert A.watcher_halted(3, 3) is True
    assert A.watcher_halted(4, 3) is True       # a manual re-run that fails again
    assert A.watcher_halted(None, 3) is False


def test_a_delivered_brief_or_one_with_no_data_is_not_a_failure():
    assert A.brief_failure({"sent": True, "delivered": 1}) is None
    assert A.brief_failure({"sent": False, "reason": "no_data"}) is None


def test_a_brief_nobody_is_set_up_to_receive_is_a_failure():
    assert "no recipients" in A.brief_failure({"sent": False, "reason": "no_recipients"})


def test_a_brief_that_failed_for_every_recipient_names_the_errors():
    reason = A.brief_failure({"sent": False, "recipients": 2, "results": [
        {"to": "a@x", "sent": False, "error": "HTTP 403"},
        {"to": "b@x", "sent": False, "error": "HTTP 403"}]})
    assert reason == "delivery failed for all 2 recipients: HTTP 403"


def test_a_brief_that_raised_while_building_is_a_failure():
    assert "could not be built" in A.brief_failure({"sent": False, "error": "boom"})


def test_the_alert_email_says_what_where_and_when_it_will_next_speak():
    subj, body = A.compose("sync_failed", "Sync failing: ar_aging for kbrushes",
                           "Error: timeout", company_id="kbrushes", cooldown=6, host="w1")
    assert subj == "[BIDE alert] Sync failing: ar_aging for kbrushes"
    assert "Error: timeout" in body and "kbrushes" in body and "6 hours" in body


# ── raise_alert, against fakes ────────────────────────────────────────────
class _Cur:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        sql = " ".join(sql.split())
        self.conn.sql.append((sql, params))
        if sql.startswith("INSERT INTO alerts") and self.conn.claim_raises:
            raise RuntimeError('relation "alerts" does not exist')

    def fetchone(self):
        return (self.conn.last_sent_at,)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self, last_sent_at=None, claim_raises=False):
        self.last_sent_at = last_sent_at
        self.claim_raises = claim_raises
        self.sql = []
        self.commits = 0
        self.closed = False

    def cursor(self):
        return _Cur(self)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True

    def updates(self):
        return [s for s in self.sql if s[0].startswith("UPDATE alerts")]


@pytest.fixture
def outbox(monkeypatch):
    sent = []

    def fake_send(to, subject, body):
        sent.append((to, subject, body))
        return {"sent": True, "provider": "fake", "to": to}

    from vinayak import notify
    monkeypatch.setattr(notify, "send_email", fake_send)
    monkeypatch.setenv("ALERT_EMAIL", "ops@bide.in, owner@bide.in")
    monkeypatch.delenv("ALERT_COOLDOWN_HOURS", raising=False)
    A._local_sent.clear()
    return sent


def test_a_new_condition_is_emailed_to_every_recipient_and_marked_sent(monkeypatch, outbox):
    conn = _Conn(last_sent_at=None)
    monkeypatch.setattr(A, "_connect", lambda: conn)
    res = A.sync_failed("kbrushes", "ar_aging", "timeout")
    assert res["sent"] is True
    assert [to for to, _, _ in outbox] == ["ops@bide.in", "owner@bide.in"]
    assert conn.sql[0][1][0] == "sync_failed:kbrushes:ar_aging"     # the dedupe key
    assert conn.sql[0][1][2] == "kbrushes"                          # scoped to the workspace
    assert "last_sent_at = %s, times_sent = times_sent + 1" in conn.updates()[0][0]
    assert conn.closed


def test_a_condition_emailed_an_hour_ago_is_recorded_but_not_emailed(monkeypatch, outbox):
    conn = _Conn(last_sent_at=datetime.now(timezone.utc) - timedelta(hours=1))
    monkeypatch.setattr(A, "_connect", lambda: conn)
    res = A.sync_failed("kbrushes", "ar_aging", "timeout")
    assert res.get("suppressed") is True
    assert outbox == []
    assert conn.commits == 1                  # times_seen is kept, the row lock released
    assert conn.updates() == []


def test_a_failed_delivery_restores_the_cooldown_so_the_next_occurrence_retries(monkeypatch, outbox):
    from vinayak import notify
    monkeypatch.setattr(notify, "send_email",
                        lambda to, s, b: {"sent": False, "error": "HTTP 500"})
    before = datetime.now(timezone.utc) - timedelta(hours=9)
    conn = _Conn(last_sent_at=before)
    monkeypatch.setattr(A, "_connect", lambda: conn)
    res = A.job_error("ar_aging_hourly", "boom")
    assert res["sent"] is False and "HTTP 500" in res["error"]
    restore = conn.updates()[-1]
    assert restore[1][0] == before and "HTTP 500" in restore[1][1]


def test_with_no_alert_email_set_the_alert_is_logged_and_not_marked_sent(monkeypatch, outbox, caplog):
    monkeypatch.delenv("ALERT_EMAIL")
    conn = _Conn(last_sent_at=None)
    monkeypatch.setattr(A, "_connect", lambda: conn)
    with caplog.at_level("ERROR"):
        res = A.brief_failed("protegere", "no recipients are set up for the brief")
    assert res == {"sent": False, "key": "brief_failed:protegere", "error": "ALERT_EMAIL is not set"}
    assert outbox == []
    assert conn.updates()[-1][1][0] is None      # last_sent_at back to never
    assert any("ALERT brief_failed" in r.getMessage() for r in caplog.records)


def test_when_the_database_is_down_process_memory_still_dedupes(monkeypatch, outbox):
    def down():
        raise RuntimeError("could not connect to server")
    monkeypatch.setattr(A, "_connect", down)
    assert A.job_error("brain_tick", "db down")["sent"] is True
    assert A.job_error("brain_tick", "db down").get("suppressed") is True
    assert len(outbox) == 2                      # one alert, two recipients


def test_when_the_alerts_table_is_missing_the_alert_still_goes_out(monkeypatch, outbox):
    conn = _Conn(claim_raises=True)
    monkeypatch.setattr(A, "_connect", lambda: conn)
    assert A.job_error("heartbeat", "x")["sent"] is True
    assert conn.closed


def test_raise_alert_never_raises_even_when_sending_explodes(monkeypatch, outbox):
    from vinayak import notify

    def explode(*a, **k):
        raise ValueError("provider exploded")
    monkeypatch.setattr(notify, "send_email", explode)
    conn = _Conn()
    monkeypatch.setattr(A, "_connect", lambda: conn)
    res = A.sync_failed("kbrushes", "grn_qir", "x")
    assert res["sent"] is False and "provider exploded" in res["error"]
    assert conn.updates()[-1][1][0] is None      # not left marked as sent


# ── the hooks do not break the jobs they watch ────────────────────────────
def test_a_failed_sync_run_alerts_and_still_raises_the_original_error(monkeypatch):
    from vinayak.pipelines import base

    class _PConn:
        def cursor(self):
            return _Cur(_Conn())

        def commit(self):
            pass

        def rollback(self):
            pass

        def close(self):
            pass

    class _P(base.BasePipeline):
        PIPELINE_NAME = "sales_invoices"
        REPORT_ID = "29"
        TABLE_NAME = "tz_sales_invoices"
        RowSchema = dict

        def _upsert(self, conn, rows, company_id):
            return 0

        def _start_run(self, conn, company_id, is_backfill):
            return 7

    def fetch_fails(*a, **k):
        raise TimeoutError("TranzAct timed out")

    raised = []

    def alert_that_also_fails(company_id, pipeline, error):
        raised.append((company_id, pipeline, error))
        raise RuntimeError("alerting is broken too")

    monkeypatch.setattr(base.psycopg2, "connect", lambda *a, **k: _PConn())
    monkeypatch.setattr(base, "fetch_report", fetch_fails)
    from vinayak import alerts
    monkeypatch.setattr(alerts, "sync_failed", alert_that_also_fails)

    with pytest.raises(TimeoutError, match="TranzAct timed out"):
        _P().run_chunk("kbrushes")
    assert raised == [("kbrushes", "sales_invoices", "TimeoutError: TranzAct timed out")]


class _RunnerCur:
    def __init__(self, errors):
        self.errors = errors
        self.last = ""

    def execute(self, sql, params=None):
        self.last = sql

    def fetchone(self):
        if "RETURNING id" in self.last:
            return (99,)
        if "RETURNING consecutive_errors" in self.last:
            return (self.errors,)
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _RunnerConn:
    def __init__(self, errors):
        self.errors = errors

    def cursor(self):
        return _RunnerCur(self.errors)

    def commit(self):
        pass

    def rollback(self):
        pass


def _failing_watcher(monkeypatch):
    from vinayak.brain import runner
    from vinayak.brain.registry import Watcher

    def boom(conn, company_id, run_id=None, config=None):
        raise ValueError("canon_invoice has no column due_date")

    w = Watcher(key="detect.test", title="Test watcher", what_it_does="", fn=boom,
                interval_minutes=60, default_config={})
    monkeypatch.setattr(runner, "by_key", lambda: {"detect.test": w})
    return runner


def test_the_failure_that_halts_a_watcher_raises_an_alert(monkeypatch):
    runner = _failing_watcher(monkeypatch)
    calls = []
    from vinayak import alerts
    monkeypatch.setattr(alerts, "watcher_halted_alert",
                        lambda cid, key, n, err: calls.append((cid, key, n)))
    res = runner.run(_RunnerConn(errors=runner.MAX_CONSECUTIVE_ERRORS), "kbrushes", "detect.test")
    assert res["status"] == "error"
    assert calls == [("kbrushes", "detect.test", runner.MAX_CONSECUTIVE_ERRORS)]


def test_a_watcher_failure_short_of_the_limit_does_not_alert(monkeypatch):
    runner = _failing_watcher(monkeypatch)
    calls = []
    from vinayak import alerts
    monkeypatch.setattr(alerts, "watcher_halted_alert", lambda *a: calls.append(a))
    runner.run(_RunnerConn(errors=1), "kbrushes", "detect.test")
    assert calls == []


def test_a_broken_alert_never_turns_a_watcher_failure_into_a_worker_crash(monkeypatch):
    runner = _failing_watcher(monkeypatch)
    from vinayak import alerts

    def broken(*a):
        raise RuntimeError("alerts broken")
    monkeypatch.setattr(alerts, "watcher_halted_alert", broken)
    res = runner.run(_RunnerConn(errors=5), "kbrushes", "detect.test")
    assert res["status"] == "error"


def test_the_scheduled_brief_alerts_only_for_workspaces_it_did_not_reach(monkeypatch):
    from vinayak import alerts, brief
    calls = []
    monkeypatch.setattr(alerts, "brief_failed", lambda cid, reason: calls.append((cid, reason)))
    brief._alert_undelivered([
        {"company_id": "kbrushes", "sent": True, "delivered": 2},
        {"company_id": "empty", "sent": False, "reason": "no_data"},
        {"company_id": "protegere", "sent": False, "recipients": 1,
         "results": [{"to": "a@x", "sent": False, "error": "email provider not configured"}]},
    ])
    assert calls == [("protegere",
                      "delivery failed for all 1 recipient: email provider not configured")]
