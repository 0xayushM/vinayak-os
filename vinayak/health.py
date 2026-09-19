"""
health.py
──────────
Is background work actually running? A heartbeat, the check that reads it,
and the payload the Sync page shows.

The worker's failure mode is silence. A crashed or wedged worker breaks no
page: the dashboard keeps serving the last figures it had, marked fresh until
the staleness threshold a day later, and the brain simply stops noticing
things. So the worker proves it is alive instead of being assumed alive —
every minute a scheduler job rewrites its row in worker_heartbeats — and
something else decides what a missing beat means.

That something cannot be the worker. A dead process does not report its own
death, and a wedged one (every thread stuck on a hung request) cannot run the
job that would notice. The check therefore runs in the API, which is a
separate service with its own lifecycle: a watchdog task started at API
startup, plus the Sync page's health endpoint, which re-runs the check each
time it is read in case the watchdog itself has died. If the API is down too,
nothing here can speak — the platform's own health probe on /health, and an
external uptime monitor, are what cover that case.

The scheduler that beats is whichever process runs APScheduler: the worker in
production, the API itself under RUN_SCHEDULER=1 in development. Both call
worker.build_scheduler, which is where the heartbeat job is added, so the
heartbeat works in either arrangement.

Env:
  HEARTBEAT_STALE_MINUTES   a beat older than this means the worker is down (default 5)
  WORKER_WATCHDOG           set to 0 to stop the API running the stale check
  WORKER_ID                 stable name for this process's heartbeat row (optional)
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
import threading
import time
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

BEAT_SECONDS = 60
PRUNE_AFTER_DAYS = 7


def stale_after_minutes() -> float:
    try:
        v = float(os.getenv("HEARTBEAT_STALE_MINUTES") or "5")
    except ValueError:
        return 5.0
    return v if v > 0 else 5.0


# ── pure ──────────────────────────────────────────────────────────────────

def worker_identity(env: dict, hostname: str, pid: int, role: str) -> dict:
    """Who is beating. The id is stable across restarts of the same service,
    so a restart updates a row (and its started_at) instead of adding one."""
    base = (env.get("WORKER_ID") or env.get("RAILWAY_REPLICA_ID") or hostname or "unknown")
    sha = (env.get("RAILWAY_GIT_COMMIT_SHA") or env.get("GIT_COMMIT_SHA")
           or env.get("SOURCE_VERSION") or "")
    return {"worker_id": f"{role}:{base}", "role": role, "hostname": hostname,
            "pid": pid, "version": sha[:12] or None}


def heartbeat_state(last_beat_at: datetime | None, now: datetime,
                    stale_after: float) -> str:
    """alive · stale · never."""
    if last_beat_at is None:
        return "never"
    if now - last_beat_at <= timedelta(minutes=stale_after):
        return "alive"
    return "stale"


def stale_alert_due(state: str, checker_uptime: timedelta, stale_after: float) -> bool:
    """Should the checker raise the worker-down alert?

    'stale' always. 'never' only once the checker itself has been up longer
    than the stale window: straight after a deploy the API routinely starts
    before the worker's first beat, and that is not an outage. A worker that
    has still never beaten after that is one that was never started — which is
    exactly the misconfiguration worth an email."""
    if state == "stale":
        return True
    if state == "never":
        return checker_uptime > timedelta(minutes=stale_after)
    return False


def feed_summary(pipelines: list[dict]) -> dict:
    """Split sync-health rows into what the panel needs to say."""
    failing = [p for p in pipelines if p.get("status") in ("failed", "error")]
    stale = [p for p in pipelines if p.get("stale") and p not in failing]
    last = max((p.get("completed_at") for p in pipelines if p.get("completed_at")),
               default=None)
    return {
        "failing": [{"pipeline_name": p.get("pipeline_name"),
                     "completed_at": p.get("completed_at"),
                     "error_message": p.get("error_message")} for p in failing],
        "stale": [{"pipeline_name": p.get("pipeline_name"),
                   "completed_at": p.get("completed_at")} for p in stale],
        "last_completed_at": last,
        "feeds": [{"pipeline_name": p.get("pipeline_name"), "status": p.get("status"),
                   "completed_at": p.get("completed_at"), "stale": bool(p.get("stale"))}
                  for p in pipelines],
    }


# ── the beat (runs in the scheduler process) ──────────────────────────────

def beat(conn, identity: dict, started_at: datetime, jobs: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO worker_heartbeats
                 (worker_id, role, hostname, pid, version, started_at, last_beat_at, jobs, beats)
               VALUES (%s,%s,%s,%s,%s,%s,NOW(),%s,1)
               ON CONFLICT (worker_id) DO UPDATE SET
                 role = EXCLUDED.role, hostname = EXCLUDED.hostname, pid = EXCLUDED.pid,
                 version = EXCLUDED.version, started_at = EXCLUDED.started_at,
                 last_beat_at = NOW(), jobs = EXCLUDED.jobs,
                 beats = worker_heartbeats.beats + 1""",
            (identity["worker_id"], identity["role"], identity["hostname"],
             identity["pid"], identity["version"], started_at, jobs))
        cur.execute(
            "DELETE FROM worker_heartbeats WHERE last_beat_at < NOW() - (%s * INTERVAL '1 day')",
            (PRUNE_AFTER_DAYS,))
    conn.commit()


def make_heartbeat_job(role: str, jobs_count):
    """The scheduler job. `jobs_count` is a callable so the count is read at
    beat time. A failed beat is logged and nothing else: the API's check is
    what turns missing beats into an alert."""
    identity = worker_identity(dict(os.environ), socket.gethostname(), os.getpid(), role)
    started_at = datetime.now(timezone.utc)

    def _heartbeat() -> None:
        conn = None
        try:
            import psycopg2
            from vinayak.config import DATABASE_URL
            conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
            beat(conn, identity, started_at, int(jobs_count()))
        except Exception as exc:  # noqa: BLE001
            logger.warning("heartbeat failed: %s", exc)
        finally:
            if conn is not None:
                conn.close()

    return _heartbeat


# ── reading it (runs in the API) ──────────────────────────────────────────

def _iso(ts):
    return ts.isoformat() if ts else None


def pick_heartbeat(rows: list[tuple]) -> tuple | None:
    """Which heartbeat speaks for "the worker".

    rows are (worker_id, role, ..., last_beat_at at index 5, ...). A 'worker'
    row wins over an 'api' one whatever their ages: a developer running the
    API with RUN_SCHEDULER=1 against a shared database beats too, and a laptop
    must never be able to make a dead production worker look alive. Only when
    no worker has ever beaten does an API scheduler count (local development).
    """
    if not rows:
        return None
    workers = [r for r in rows if r[1] == "worker"]
    pool = workers or list(rows)
    return max(pool, key=lambda r: r[5])


def worker_status(conn, now: datetime | None = None) -> dict:
    """The worker's heartbeat, judged against the database clock (the beat is
    written with NOW(), so comparing with the API host's clock would fold
    clock skew into the answer)."""
    stale_after = stale_after_minutes()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT worker_id, role, hostname, version, started_at, last_beat_at, jobs
                 FROM worker_heartbeats ORDER BY last_beat_at DESC LIMIT 20""")
        rows = cur.fetchall()
        if now is None:
            cur.execute("SELECT NOW()")
            now = cur.fetchone()[0]
    latest = pick_heartbeat(rows)
    last_beat = latest[5] if latest else None
    state = heartbeat_state(last_beat, now, stale_after)
    # Any other scheduler beating right now. Two schedulers means every job
    # runs twice, which is worth seeing on the page.
    others = [{"worker_id": r[0], "role": r[1], "last_beat_at": _iso(r[5])}
              for r in rows
              if r is not latest and heartbeat_state(r[5], now, stale_after) == "alive"]
    return {
        "state": state,
        "alive": state == "alive",
        "last_beat_at": _iso(last_beat),
        "minutes_since_beat": (round((now - last_beat).total_seconds() / 60, 1)
                               if last_beat else None),
        "stale_after_minutes": stale_after,
        "worker_id": latest[0] if latest else None,
        "role": latest[1] if latest else None,
        "version": latest[3] if latest else None,
        "started_at": _iso(latest[4]) if latest else None,
        "jobs": int(latest[6]) if latest else None,
        "other_schedulers": others,
    }


def check_worker_stale(checker_started_at: datetime) -> dict:
    """Read the heartbeat and alert if the worker is down. Never raises."""
    conn = None
    try:
        import psycopg2
        from vinayak.config import DATABASE_URL
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
    except Exception as exc:  # noqa: BLE001
        # The database being unreachable is loud on its own (every page 503s);
        # a connection blip is not worth an email.
        logger.warning("worker stale check could not connect: %s", exc)
        return {"checked": False, "error": str(exc)}
    try:
        status = worker_status(conn)
    except Exception as exc:  # noqa: BLE001
        # Connected but cannot read heartbeats — almost always migration 025
        # not applied, which means no heartbeat is being recorded either and
        # this check is blind. Being blind is itself the alert.
        logger.error("worker stale check could not read heartbeats: %s", exc)
        from vinayak import alerts
        alerts.raise_alert(
            "worker_stale", "worker_check_failed",
            "Cannot tell whether the background worker is running",
            f"Reading worker_heartbeats failed: {exc}\n\nIs migration 025 applied? "
            f"Until this is fixed a dead worker will not be noticed.")
        return {"checked": False, "error": str(exc)}
    finally:
        conn.close()

    now = datetime.now(timezone.utc)
    stale_after = status["stale_after_minutes"]
    if not stale_alert_due(status["state"], now - checker_started_at, stale_after):
        return {"checked": True, "state": status["state"], "alerted": False}

    from vinayak import alerts
    if status["state"] == "never":
        detail = ("No background worker has ever recorded a heartbeat. Syncs, the "
                  "morning brief and the brain's watchers are probably not running. "
                  "Check that the worker service is deployed and started "
                  "(python -m vinayak.worker), and that migration 025 is applied.")
    else:
        detail = (f"The last heartbeat was {status['minutes_since_beat']} minutes ago "
                  f"(from {status['worker_id']}, version {status['version'] or 'unknown'}). "
                  f"Syncs, the morning brief and the brain's watchers are not running "
                  f"until the worker is back. Check the worker service's logs and restart it.")
    res = alerts.raise_alert("worker_stale", "worker_stale",
                             "Background worker is down", detail)
    return {"checked": True, "state": status["state"], "alerted": True, **res}


_background_lock = threading.Lock()
_last_background_check = float("-inf")


def check_worker_stale_in_background(checker_started_at: datetime) -> None:
    """Fire-and-forget, for request handlers: sending an email can take
    seconds and must not hold up the page that triggered the check. At most
    one per minute per process, however many tabs are polling."""
    global _last_background_check
    with _background_lock:
        now = time.monotonic()
        if now - _last_background_check < 60:
            return
        _last_background_check = now
    threading.Thread(target=check_worker_stale, args=(checker_started_at,),
                     daemon=True, name="worker-stale-check").start()


def watchdog_enabled() -> bool:
    return os.getenv("WORKER_WATCHDOG", "1").strip().lower() not in ("0", "false", "no")


async def watchdog(checker_started_at: datetime, every_seconds: float = 300) -> None:
    """The API's loop. Runs in every API replica; the alerts table's dedupe is
    what keeps several replicas from sending the same email."""
    await asyncio.sleep(stale_after_minutes() * 60)
    while True:
        try:
            await asyncio.to_thread(check_worker_stale, checker_started_at)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("worker watchdog pass failed: %s", exc)
        await asyncio.sleep(every_seconds)


# ── the Sync page payload ─────────────────────────────────────────────────

def worker_health(conn, company_id: str, now: datetime | None = None) -> dict:
    """Everything the Sync page's health panel shows, for one workspace.

    Each section is read independently and reports its own error: a missing
    table (a migration not applied) must show up as that sentence on the
    page, not as a blank panel or a page-wide 500 that hides the sections
    that did work."""
    from vinayak.brain.runner import MAX_CONSECUTIVE_ERRORS
    from vinayak.brain.registry import all_watchers
    from vinayak.schema import queries

    now = now or datetime.now(timezone.utc)
    out: dict = {"checked_at": now.isoformat()}

    def section(name, fn):
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001
            logger.warning("worker health: %s section failed: %s", name, exc)
            try:
                conn.rollback()
            except Exception:  # noqa: BLE001
                pass
            out[name] = {"error": str(exc).splitlines()[0][:300]}

    section("worker", lambda: worker_status(conn, now))

    def brain():
        titles = {w.key: w.title for w in all_watchers()}
        with conn.cursor() as cur:
            cur.execute(
                """SELECT started_at, status, workflow_key FROM brain_runs
                    WHERE company_id = %s ORDER BY started_at DESC LIMIT 1""",
                (company_id,))
            last = cur.fetchone()
            cur.execute(
                """SELECT workflow_key, last_error, last_run_at, consecutive_errors
                     FROM workflows
                    WHERE company_id = %s AND consecutive_errors >= %s
                    ORDER BY workflow_key""",
                (company_id, MAX_CONSECUTIVE_ERRORS))
            halted = cur.fetchall()
        return {
            "last_run_at": _iso(last[0]) if last else None,
            "last_run_status": last[1] if last else None,
            "last_run_workflow": last[2] if last else None,
            "halted": [{"key": r[0], "title": titles.get(r[0], r[0]),
                        "last_error": r[1], "last_run_at": _iso(r[2]),
                        "consecutive_errors": int(r[3] or 0)} for r in halted],
        }

    section("brain", brain)
    section("sync", lambda: feed_summary(
        queries.get_sync_health(conn, company_id).get("pipelines") or []))

    def recent_alerts():
        # This workspace's alerts and the global ones (worker down) — never
        # another workspace's.
        with conn.cursor() as cur:
            cur.execute(
                """SELECT kind, subject, company_id, first_seen_at, last_seen_at,
                          times_seen, last_sent_at, last_error
                     FROM alerts
                    WHERE (company_id = %s OR company_id IS NULL)
                      AND last_seen_at > NOW() - INTERVAL '7 days'
                    ORDER BY last_seen_at DESC LIMIT 10""", (company_id,))
            rows = cur.fetchall()
        return [{"kind": r[0], "subject": r[1], "global": r[2] is None,
                 "first_seen_at": _iso(r[3]), "last_seen_at": _iso(r[4]),
                 "times_seen": int(r[5] or 0), "last_sent_at": _iso(r[6]),
                 "email_error": r[7]} for r in rows]

    section("alerts", recent_alerts)
    return out
