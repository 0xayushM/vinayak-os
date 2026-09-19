"""
vinayak/worker.py
──────────────────
The background process. `python -m vinayak.worker` and nothing else.

Why this is a separate service rather than a thread inside the API:

  • A sync that takes four minutes should not be competing for the event loop
    with a request that has a person waiting on it.
  • The API is horizontally scaled; a scheduler inside it would run every job
    once per replica. Today there is one replica, which is exactly the kind of
    accident that is invisible until the day there are two.
  • Background work can be redeployed, restarted and rolled back without
    dropping a request, and a crash loop in a watcher cannot take the
    dashboard down with it.

What it runs:
  • the ten sync pipelines and the morning brief, on the existing schedule
  • a brain tick every few minutes: for each connected company, run whichever
    watchers are due (brain/runner.py decides), inside a brain_runs episode
  • a heartbeat every minute into worker_heartbeats, so the API can tell a
    running worker from a dead one (health.py) — silence is this process's
    only failure mode, so it has to keep proving it is not silent

Deployment: a second Railway service off the same repo, with the same
environment, whose dashboard start command is this module and whose
healthcheck path is empty (see Procfile). The API service leaves RUN_SCHEDULER unset so it
no longer runs the jobs itself.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime, timezone

import psycopg2

from vinayak.config import DATABASE_URL, env_int

from vinayak.logs import configure_logging, company_id_var

configure_logging()
logger = logging.getLogger("vinayak.worker")

BRAIN_TICK_MINUTES = env_int("BRAIN_TICK_MINUTES", 10)


def companies() -> list[str]:
    """Every workspace the worker should think about. A company with no
    connection yet has no data to watch, so it is skipped rather than being
    given an hourly run that can only ever find nothing."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT DISTINCT company_id FROM tool_connections
                    WHERE is_active = TRUE ORDER BY 1""")
            return [r[0] for r in cur.fetchall()]
    finally:
        conn.close()


def brain_tick() -> None:
    """One pass over every company. A failure for one never touches another —
    each gets its own connection and its own try."""
    from vinayak.brain import runner

    ids = companies()
    if not ids:
        logger.info("brain tick: no connected workspaces")
        return
    for company_id in ids:
        conn = None
        token = company_id_var.set(company_id)       # log lines carry the workspace
        try:
            conn = psycopg2.connect(DATABASE_URL)
            runs = runner.run_due(conn, company_id)
            if runs:
                logger.info("brain tick %s: %s", company_id,
                            "; ".join(r.get("summary") or r["status"] for r in runs))
        except Exception as exc:  # noqa: BLE001
            logger.exception("brain tick failed for %s: %s", company_id, exc)
        finally:
            company_id_var.reset(token)
            if conn is not None:
                conn.close()


def _on_job_error(event) -> None:
    """A job that raised past its own handlers. Every job here catches its
    own failures, so reaching this means a failure nobody planned for — the
    kind that otherwise shows up only as a traceback in a log nobody reads."""
    from vinayak import alerts
    try:
        logger.error("job %s raised: %s", event.job_id, event.exception)
        alerts.job_error(event.job_id, f"{type(event.exception).__name__}: {event.exception}")
    except Exception:  # noqa: BLE001 — a listener must never break the scheduler
        logger.exception("job error listener failed")


def build_scheduler(role: str = "worker"):
    """The sync jobs, the brief, the brain tick and the heartbeat on one
    scheduler. `role` names the heartbeat: 'worker' for this process, 'api'
    when the API runs the scheduler itself (RUN_SCHEDULER=1)."""
    from apscheduler.events import EVENT_JOB_ERROR
    from apscheduler.triggers.interval import IntervalTrigger
    from vinayak import health
    from vinayak.pipelines.scheduler import scheduler

    scheduler.add_job(
        brain_tick,
        trigger=IntervalTrigger(minutes=BRAIN_TICK_MINUTES),
        id="brain_tick",
        name=f"Brain tick (every {BRAIN_TICK_MINUTES} min)",
        replace_existing=True,
        max_instances=1,             # a slow tick waits, it does not stack up
        misfire_grace_time=300,
        coalesce=True,
    )
    scheduler.add_job(
        health.make_heartbeat_job(role, lambda: len(scheduler.get_jobs())),
        trigger=IntervalTrigger(seconds=health.BEAT_SECONDS),
        id="heartbeat",
        name="Heartbeat (every minute)",
        replace_existing=True,
        max_instances=1,
        misfire_grace_time=60,
        coalesce=True,
        next_run_time=datetime.now(timezone.utc),   # beat at startup, not a minute later
    )
    scheduler.remove_listener(_on_job_error)       # idempotent if built twice
    scheduler.add_listener(_on_job_error, EVENT_JOB_ERROR)
    return scheduler


async def _main() -> None:
    from vinayak.pipelines.scheduler import start_scheduler, stop_scheduler

    from vinayak.scripts.migrate import warn_if_pending
    warn_if_pending(logger)

    scheduler = build_scheduler()
    start_scheduler()
    logger.info("Worker up — %d jobs", len(scheduler.get_jobs()))

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:      # pragma: no cover — Windows
            pass
    await stop.wait()

    logger.info("Worker shutting down…")
    stop_scheduler()


def main() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:            # pragma: no cover
        pass


if __name__ == "__main__":
    main()
