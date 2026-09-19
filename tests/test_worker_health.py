"""
A dead worker must be noticed by something other than the worker. The
judgements — alive or not, alert or not, which heartbeat speaks for the
worker — are pure and tested here; the reads run against fake connections.
Nothing here opens a database.
"""
from datetime import datetime, timedelta, timezone

import pytest

from vinayak import health as H

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=timezone.utc)


# ── pure ──────────────────────────────────────────────────────────────────
def test_a_beat_inside_the_window_is_alive_and_one_outside_is_stale():
    assert H.heartbeat_state(NOW - timedelta(minutes=4), NOW, 5) == "alive"
    assert H.heartbeat_state(NOW - timedelta(minutes=5), NOW, 5) == "alive"
    assert H.heartbeat_state(NOW - timedelta(minutes=6), NOW, 5) == "stale"
    assert H.heartbeat_state(None, NOW, 5) == "never"


def test_a_stale_worker_always_alerts():
    assert H.stale_alert_due("stale", timedelta(seconds=1), 5) is True


def test_a_worker_that_has_never_beaten_is_not_an_outage_straight_after_a_deploy():
    assert H.stale_alert_due("never", timedelta(minutes=3), 5) is False


def test_a_worker_that_has_still_never_beaten_after_the_window_was_never_started():
    assert H.stale_alert_due("never", timedelta(minutes=6), 5) is True


def test_an_alive_worker_never_alerts():
    assert H.stale_alert_due("alive", timedelta(days=3), 5) is False


def test_the_heartbeat_identity_is_stable_across_restarts_and_carries_the_git_sha():
    env = {"RAILWAY_REPLICA_ID": "r-123", "RAILWAY_GIT_COMMIT_SHA": "605cae569bc6e10f6b1fb5e2"}
    a = H.worker_identity(env, "host-a", 10, "worker")
    b = H.worker_identity(env, "host-b", 99, "worker")
    assert a["worker_id"] == b["worker_id"] == "worker:r-123"
    assert a["version"] == "605cae569bc6"
    assert H.worker_identity({"WORKER_ID": "w1"}, "h", 1, "api")["worker_id"] == "api:w1"
    assert H.worker_identity({}, "laptop", 1, "api") == {
        "worker_id": "api:laptop", "role": "api", "hostname": "laptop", "pid": 1, "version": None}


def _row(worker_id, role, beat):
    return (worker_id, role, "host", "sha", beat - timedelta(hours=1), beat, 14)


def test_a_developer_api_scheduler_cannot_make_a_dead_worker_look_alive():
    rows = [_row("api:laptop", "api", NOW),
            _row("worker:prod", "worker", NOW - timedelta(hours=2))]
    assert H.pick_heartbeat(rows)[0] == "worker:prod"


def test_with_no_worker_ever_the_api_scheduler_speaks_for_background_work():
    rows = [_row("api:old", "api", NOW - timedelta(hours=1)), _row("api:laptop", "api", NOW)]
    assert H.pick_heartbeat(rows)[0] == "api:laptop"
    assert H.pick_heartbeat([]) is None


def test_feed_summary_separates_failing_from_merely_stale():
    s = H.feed_summary([
        {"pipeline_name": "ar_aging", "status": "success", "completed_at": "2026-11-12T08:00:00+00:00", "stale": False},
        {"pipeline_name": "grn_qir", "status": "failed", "completed_at": "2026-11-12T07:00:00+00:00",
         "error_message": "HTTP 502", "stale": True},
        {"pipeline_name": "sales_orders", "status": "success", "completed_at": "2026-11-10T07:00:00+00:00", "stale": True},
    ])
    assert [f["pipeline_name"] for f in s["failing"]] == ["grn_qir"]
    assert s["failing"][0]["error_message"] == "HTTP 502"
    assert [f["pipeline_name"] for f in s["stale"]] == ["sales_orders"]
    assert s["last_completed_at"] == "2026-11-12T08:00:00+00:00"
    assert len(s["feeds"]) == 3


# ── reads against fakes ───────────────────────────────────────────────────
class _Cur:
    def __init__(self, conn):
        self.conn = conn
        self.sql = ""

    def execute(self, sql, params=None):
        self.sql = " ".join(sql.split())
        self.conn.executed.append((self.sql, params))
        for needle in self.conn.fail_on:
            if needle in self.sql:
                raise RuntimeError(f'relation "{needle}" does not exist')

    def fetchall(self):
        if "FROM worker_heartbeats" in self.sql:
            return self.conn.beats
        if "FROM workflows" in self.sql:
            return [("detect.overdue_rung", "division by zero", NOW, 3)]
        if "FROM alerts" in self.sql:
            return [("worker_stale", "Background worker is down", None, NOW, NOW, 2, NOW, None)]
        return []

    def fetchone(self):
        if self.sql == "SELECT NOW()":
            return (NOW,)
        if "FROM brain_runs" in self.sql:
            return (NOW - timedelta(minutes=8), "ok", "detect.overdue_rung")
        return None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Conn:
    def __init__(self, beats=(), fail_on=()):
        self.beats = list(beats)
        self.fail_on = list(fail_on)
        self.executed = []
        self.rollbacks = 0

    def cursor(self):
        return _Cur(self)

    def rollback(self):
        self.rollbacks += 1

    def commit(self):
        pass

    def close(self):
        pass


def test_worker_status_judges_the_beat_against_the_database_clock(monkeypatch):
    monkeypatch.delenv("HEARTBEAT_STALE_MINUTES", raising=False)
    conn = _Conn(beats=[_row("worker:prod", "worker", NOW - timedelta(minutes=2)),
                        _row("api:laptop", "api", NOW - timedelta(minutes=1))])
    s = H.worker_status(conn)
    assert s["state"] == "alive" and s["alive"] is True
    assert s["worker_id"] == "worker:prod"
    assert s["minutes_since_beat"] == 2.0
    assert s["other_schedulers"] == [{"worker_id": "api:laptop", "role": "api",
                                      "last_beat_at": (NOW - timedelta(minutes=1)).isoformat()}]


def test_the_health_payload_reports_a_broken_section_without_hiding_the_others(monkeypatch):
    from vinayak.schema import queries
    monkeypatch.setattr(queries, "get_sync_health", lambda conn, cid: {"pipelines": [
        {"pipeline_name": "grn_qir", "status": "failed", "completed_at": None,
         "error_message": "HTTP 502", "stale": True}]})
    conn = _Conn(beats=[], fail_on=["worker_heartbeats"])       # migration 025 not applied
    out = H.worker_health(conn, "kbrushes", now=NOW)
    assert "worker_heartbeats" in out["worker"]["error"]
    assert conn.rollbacks == 1
    assert out["brain"]["halted"][0]["key"] == "detect.overdue_rung"
    assert out["brain"]["last_run_status"] == "ok"
    assert out["sync"]["failing"][0]["pipeline_name"] == "grn_qir"
    assert out["alerts"][0]["global"] is True


def test_the_health_payload_only_reads_this_workspaces_alerts_and_the_global_ones(monkeypatch):
    from vinayak.schema import queries
    monkeypatch.setattr(queries, "get_sync_health", lambda conn, cid: {"pipelines": []})
    conn = _Conn()
    H.worker_health(conn, "protegere", now=NOW)
    sql, params = next(e for e in conn.executed if "FROM alerts" in e[0])
    assert "(company_id = %s OR company_id IS NULL)" in sql
    assert params == ("protegere",)
    sql, params = next(e for e in conn.executed if "FROM workflows" in e[0])
    assert params[0] == "protegere"


def test_a_stale_worker_raises_the_worker_down_alert(monkeypatch):
    import psycopg2
    from vinayak import alerts
    monkeypatch.setattr(psycopg2, "connect", lambda *a, **k: _Conn(
        beats=[_row("worker:prod", "worker", NOW - timedelta(minutes=30))]))
    calls = []
    monkeypatch.setattr(alerts, "raise_alert",
                        lambda kind, key, subject, detail="", **k: calls.append((kind, key, detail)) or {"sent": True})
    res = H.check_worker_stale(datetime.now(timezone.utc) - timedelta(hours=1))
    assert res["alerted"] is True
    assert calls[0][:2] == ("worker_stale", "worker_stale")
    assert "30.0 minutes ago" in calls[0][2]


def test_the_stale_check_never_raises_when_the_database_is_unreachable(monkeypatch):
    import psycopg2

    def down(*a, **k):
        raise psycopg2.OperationalError("could not connect")
    monkeypatch.setattr(psycopg2, "connect", down)
    assert H.check_worker_stale(NOW)["checked"] is False


def test_the_heartbeat_upserts_its_row_and_prunes_long_dead_ones():
    conn = _Conn()
    ident = H.worker_identity({"WORKER_ID": "w"}, "h", 1, "worker")
    H.beat(conn, ident, NOW, 14)
    assert "ON CONFLICT (worker_id) DO UPDATE" in conn.executed[0][0]
    assert conn.executed[0][1][0] == "worker:w"
    assert conn.executed[1][0].startswith("DELETE FROM worker_heartbeats")


def test_a_failed_heartbeat_is_logged_and_never_raises(monkeypatch):
    import psycopg2

    def down(*a, **k):
        raise psycopg2.OperationalError("could not connect")
    monkeypatch.setattr(psycopg2, "connect", down)
    H.make_heartbeat_job("worker", lambda: 3)()


def test_the_scheduler_beats_and_turns_unhandled_job_errors_into_alerts(monkeypatch):
    from vinayak import alerts, worker
    sched = worker.build_scheduler(role="api")
    job = sched.get_job("heartbeat")
    assert job is not None and job.max_instances == 1
    assert sched.get_job("brain_tick") is not None

    calls = []
    monkeypatch.setattr(alerts, "job_error", lambda job_id, err: calls.append((job_id, err)))

    class _Event:
        job_id = "ar_aging_hourly"
        exception = KeyError("email")
    worker._on_job_error(_Event())
    assert calls == [("ar_aging_hourly", "KeyError: 'email'")]

    def broken(*a):
        raise RuntimeError("alerts broken")
    monkeypatch.setattr(alerts, "job_error", broken)
    worker._on_job_error(_Event())                  # must not raise into the scheduler


def test_a_check_that_cannot_read_heartbeats_is_blind_and_says_so(monkeypatch):
    import psycopg2
    from vinayak import alerts
    monkeypatch.setattr(psycopg2, "connect",
                        lambda *a, **k: _Conn(fail_on=["worker_heartbeats"]))
    calls = []
    monkeypatch.setattr(alerts, "raise_alert",
                        lambda kind, key, subject, detail="", **k: calls.append(key) or {})
    assert H.check_worker_stale(NOW)["checked"] is False
    assert calls == ["worker_check_failed"]
