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

Deployment: a second Railway service off the same image, with the same
environment, whose start command is this module. The API service sets
RUN_SCHEDULER=0 so it no longer runs the jobs itself.
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal

import psycopg2

from vinayak.config import DATABASE_URL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
)
logger = logging.getLogger("vinayak.worker")

BRAIN_TICK_MINUTES = int(os.getenv("BRAIN_TICK_MINUTES", "10"))


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
        try:
            conn = psycopg2.connect(DATABASE_URL)
            runs = runner.run_due(conn, company_id)
            if runs:
                logger.info("brain tick %s: %s", company_id,
                            "; ".join(r.get("summary") or r["status"] for r in runs))
        except Exception as exc:  # noqa: BLE001
            logger.exception("brain tick failed for %s: %s", company_id, exc)
        finally:
            if conn is not None:
                conn.close()


def build_scheduler():
    """The sync jobs, the brief, and the brain tick on one scheduler."""
    from apscheduler.triggers.interval import IntervalTrigger
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
    return scheduler


async def _main() -> None:
    from vinayak.pipelines.scheduler import start_scheduler, stop_scheduler

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
