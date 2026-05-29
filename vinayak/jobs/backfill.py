"""
jobs/backfill.py
─────────────────
Backward history backfill.

The initial connect-time sync pulls only the most recent month so the
dashboard lights up fast. This job walks each pipeline's history one window
further into the past per run, until it reaches a floor (default: 12 months
of history). It is safe to run repeatedly — each run advances the watermark a
little further back, and stops cleanly once the floor is reached.

Two entrypoints:

  • backfill_company(company_id, months=1, floor_months=12)
        Run one backward step for every pipeline of one company.
        Called by the on-demand "load more history" endpoint and by the cron.

  • main()  (python -m vinayak.jobs.backfill)
        Loop over every active TranzAct connection and back-fill each.
        Wire this to a scheduler (Railway cron, GitHub Action, system cron).

Rate-limit note: the global throttle in adapters/tranzact/client.py is shared,
so pipelines here still run SERIALLY. Do not fan companies out concurrently —
they share the same 10 req/min/machine budget.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import psycopg2

from vinayak.config import DATABASE_URL, TRANZACT_BASE_URL

logger = logging.getLogger(__name__)

# One "month" window. Reports are fetched per-window; a bigger step backfills
# faster but issues more requests per run.
WINDOW_DAYS = 30


# ── Per-company backfill ────────────────────────────────────────────────────

def backfill_company(
    company_id: str,
    email: str,
    password: str,
    months: int = 1,
    floor_months: int = 12,
) -> dict:
    """
    Advance every pipeline's history `months` further into the past for one
    company. Returns a per-pipeline summary dict.

    For each pipeline:
      • oldest = watermark (oldest_fetched_date); if never run, treat as today
        so the first backward step covers the month before the initial sync.
      • floor  = per-pipeline floor_date if set, else today - floor_months*30.
      • If oldest is already at/under the floor → nothing to do.
      • Otherwise fetch the window [max(oldest - months*30, floor), oldest - 1].
        run() moves the watermark back automatically on success.
    """
    # Imported lazily to avoid importing the FastAPI app at module load.
    from vinayak.api.routes.connections import _full_sync_plan
    from vinayak.adapters.tranzact.auth import get_access_token

    today = date.today()
    floor_default = today - timedelta(days=floor_months * WINDOW_DAYS)
    step = timedelta(days=months * WINDOW_DAYS)

    # Prime the in-memory token cache with THIS company's credentials.
    get_access_token(
        base_url=TRANZACT_BASE_URL,
        email=email,
        password=password,
        force_refresh=True,
    )

    summary: dict[str, str] = {}
    conn = psycopg2.connect(DATABASE_URL)
    try:
        for PipelineCls, _days_back, key, _label in _full_sync_plan():
            oldest = PipelineCls.get_oldest_fetched_date(conn, company_id) or today
            floor = PipelineCls.get_backfill_floor(conn, company_id) or floor_default

            if oldest <= floor:
                summary[key] = f"complete (history back to {oldest})"
                continue

            window_to = oldest - timedelta(days=1)
            window_from = max(oldest - step, floor)

            logger.info(
                "%s backfill [%s]: %s → %s (floor %s)",
                key, company_id, window_from, window_to, floor,
            )
            try:
                rows = PipelineCls().run(
                    window_from, window_to, is_backfill=True, company_id=company_id
                )
                summary[key] = f"fetched {window_from}→{window_to} ({rows} rows)"
            except Exception as exc:  # noqa: BLE001
                logger.error("%s backfill failed: %s", key, exc)
                summary[key] = f"failed: {exc}"
    finally:
        conn.close()

    return summary


# ── Multi-tenant cron entrypoint ────────────────────────────────────────────

def _active_tranzact_companies() -> list[tuple[str, str]]:
    """Return [(company_id, encrypted_credentials)] for active TranzAct conns."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT company_id, encrypted_credentials
                     FROM tool_connections
                    WHERE tool_name = 'tranzact' AND is_active = TRUE
                      AND encrypted_credentials IS NOT NULL"""
            )
            return cur.fetchall()
    finally:
        conn.close()


def main(months: int = 1, floor_months: int = 12) -> None:
    """
    Cron entrypoint: back-fill one window for every active TranzAct company,
    sequentially (shared rate limit).

    Usage:
        python -m vinayak.jobs.backfill
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    from vinayak.api.routes.connections import _decrypt

    companies = _active_tranzact_companies()
    if not companies:
        logger.info("No active TranzAct connections to back-fill.")
        return

    logger.info("Backfilling %d company(ies)…", len(companies))
    for company_id, blob in companies:
        try:
            creds = _decrypt(blob)
        except Exception as exc:  # noqa: BLE001
            logger.error("Could not decrypt credentials for %s: %s", company_id, exc)
            continue
        summary = backfill_company(
            company_id, creds["email"], creds["password"],
            months=months, floor_months=floor_months,
        )
        logger.info("%s backfill summary: %s", company_id, summary)


if __name__ == "__main__":
    main()
