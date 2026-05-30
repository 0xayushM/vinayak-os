"""
pipelines/base.py
──────────────────
BasePipeline — all 10 concrete pipelines inherit from this class.

Subclasses must define:
    PIPELINE_NAME : str   (matches tz_sync_runs.pipeline_name)
    REPORT_ID     : str   (TranzAct report ID, e.g. "29")
    TABLE_NAME    : str   (Postgres table, e.g. "tz_sales_invoices")
    RowSchema     : type  (Pydantic BaseModel for one row)

Subclasses must implement:
    _get_filters(from_date, to_date) -> dict
        Returns the filters dict to pass to fetch_report().
    _upsert(conn, rows) -> int
        Performs the INSERT … ON CONFLICT DO UPDATE and returns rows upserted.

The run() method provides the full pipeline contract:
    fetch → validate → upsert → log → error handling
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from datetime import date, timedelta
from typing import Type

import psycopg2
import psycopg2.extras

from vinayak.adapters.tranzact.client import TranzactCreds, fetch_report
from vinayak.config import DATABASE_URL

logger = logging.getLogger(__name__)


class BasePipeline(ABC):

    PIPELINE_NAME: str
    REPORT_ID: str
    TABLE_NAME: str
    RowSchema: type  # Pydantic model

    # Name of the RowSchema attribute that the from_date/to_date filter applies
    # to (the record's primary date). Used to compute the true coverage floor
    # when a fetch is cut short by the time cap. Leave None for snapshot reports
    # (inventory/process routing) that have no date window.
    DATE_FILTER_FIELD: str | None = None

    # ── Public methods ────────────────────────────────────────────────────────

    def run(
        self,
        from_date: date,
        to_date: date,
        is_backfill: bool = False,
        company_id: str = "protegere",
        max_seconds: float | None = None,
        creds: TranzactCreds | None = None,
    ) -> int:
        """
        Full pipeline run:
          1. Open a DB connection and log 'running' to tz_sync_runs
          2. Fetch all rows from TranzAct
          3. Validate rows with Pydantic (bad rows are skipped, not raised)
          4. Upsert valid rows into the cached table
          5. Update tz_sync_runs with 'success' or 'failed'
          6. Move the backfill watermark back if this run reached further into
             the past than any previous run.

        Returns the number of rows upserted.
        """
        conn = psycopg2.connect(DATABASE_URL)
        run_id = self._start_run(conn, is_backfill)
        rows_fetched = 0
        rows_upserted = 0
        try:
            filters = self._get_filters(str(from_date), str(to_date))
            stats: dict = {}
            raw_rows = fetch_report(
                self.REPORT_ID, filters, max_seconds=max_seconds, stats=stats,
                creds=creds,
            )
            rows_fetched = len(raw_rows)

            validated = self._validate(raw_rows)
            self._upsert(conn, validated, company_id)
            rows_upserted = len(validated)  # execute_values rowcount unreliable with page_size batching

            # Record how far back this run actually reached. Rows come back
            # newest-first, so a complete fetch covers the whole window down to
            # from_date. A time-capped (truncated) fetch only has the most recent
            # rows — its coverage floor is the OLDEST record date we managed to
            # pull, NOT from_date. Recording the real floor lets the backfill
            # resume from exactly there instead of skipping the unfetched span.
            coverage_floor = self._coverage_floor(from_date, validated, stats)
            self._touch_backfill_state(conn, company_id, coverage_floor)
            self._finish_run(conn, run_id, "success", rows_fetched, rows_upserted)
            if stats.get("truncated"):
                logger.warning(
                    "%s: ⏱  time-capped — coverage floor recorded as %s "
                    "(window start was %s); backfill will continue from there",
                    self.PIPELINE_NAME, coverage_floor, from_date,
                )
            logger.info(
                "%s: ✅  fetched=%d upserted=%d",
                self.PIPELINE_NAME, rows_fetched, rows_upserted,
            )
            return rows_upserted
        except Exception as exc:
            self._fail_run(conn, run_id, str(exc))
            logger.error("%s: ❌  %s", self.PIPELINE_NAME, exc)
            raise
        finally:
            conn.close()

    def backfill(
        self,
        from_date: date,
        window_days: int = 30,
        sleep_between_windows: float = 1.0,
        company_id: str = "protegere",
        creds: TranzactCreds | None = None,
    ) -> None:
        """
        Split the period from_date → today into windows and run each.

        Args:
            from_date:              First date to backfill from (e.g. date(2025, 11, 1))
            window_days:            Size of each fetch window (default 30 days)
            sleep_between_windows:  Seconds to sleep between windows (rate limit safety)
        """
        today = date.today()
        cursor = from_date
        window_count = 0

        while cursor < today:
            end = min(cursor + timedelta(days=window_days - 1), today)
            logger.info(
                "%s backfill: window %d — %s → %s",
                self.PIPELINE_NAME, window_count + 1, cursor, end,
            )
            self.run(cursor, end, is_backfill=True, company_id=company_id, creds=creds)
            cursor = end + timedelta(days=1)
            window_count += 1
            if cursor < today and sleep_between_windows > 0:
                time.sleep(sleep_between_windows)

        logger.info("%s backfill: complete — %d windows", self.PIPELINE_NAME, window_count)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _validate(self, raw_rows: list[dict]) -> list:
        """
        Run each row through RowSchema Pydantic validation.
        Bad rows are logged and skipped — a failed row never crashes the pipeline.
        Returns a list of validated Pydantic model instances.
        """
        valid, skipped = [], 0
        for row in raw_rows:
            try:
                valid.append(self.RowSchema(**row))
            except Exception as exc:
                skipped += 1
                logger.debug(
                    "%s: skipped invalid row (%s) | row=%s",
                    self.PIPELINE_NAME, exc, row,
                )
        if skipped:
            logger.warning(
                "%s: %d/%d rows skipped during validation",
                self.PIPELINE_NAME, skipped, len(raw_rows),
            )
        return valid

    def _start_run(self, conn, is_backfill: bool) -> int:
        """Insert a 'running' row into tz_sync_runs. Returns the run ID."""
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tz_sync_runs
                       (pipeline_name, report_id, status, is_backfill)
                   VALUES (%s, %s, 'running', %s)
                   RETURNING id""",
                (self.PIPELINE_NAME, int(self.REPORT_ID), is_backfill),
            )
            run_id = cur.fetchone()[0]
        conn.commit()
        return run_id

    def _finish_run(self, conn, run_id: int, status: str,
                    rows_fetched: int, rows_upserted: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE tz_sync_runs
                   SET status=%s, rows_fetched=%s, rows_upserted=%s,
                       completed_at=NOW()
                   WHERE id=%s""",
                (status, rows_fetched, rows_upserted, run_id),
            )
        conn.commit()

    def _fail_run(self, conn, run_id: int, error_message: str) -> None:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tz_sync_runs
                       SET status='failed', error_message=%s, completed_at=NOW()
                       WHERE id=%s""",
                    (error_message[:2000], run_id),
                )
            conn.commit()
        except Exception as log_exc:
            logger.error("Could not log pipeline failure: %s", log_exc)

    @classmethod
    def get_last_success_date(cls, conn, company_id: str = "protegere") -> date | None:
        """
        Query tz_sync_runs for the completed_at date of the most recent
        successful run of this pipeline for this brand. Returns None if no run
        exists.
        """
        with conn.cursor() as cur:
            cur.execute(
                """SELECT completed_at
                     FROM tz_sync_runs
                    WHERE pipeline_name = %s
                      AND company_id = %s
                      AND status = 'success'
                    ORDER BY completed_at DESC
                    LIMIT 1""",
                (cls.PIPELINE_NAME, company_id),
            )
            row = cur.fetchone()
        if row and row[0]:
            return row[0].date() if hasattr(row[0], "date") else row[0]
        return None

    # ── Backfill watermark ─────────────────────────────────────────────────────

    def _coverage_floor(self, from_date: date, validated: list, stats: dict) -> date:
        """
        Decide the oldest date this run can claim to have fetched.

        • Complete fetch (not truncated), or a snapshot report with no date
          field → the run covered the whole window, so the floor is from_date.
        • Truncated fetch → rows are newest-first, so we only have the recent
          tail. The real floor is the OLDEST record date among the rows we got.
          If no dated rows came back, fall back to to-date semantics by claiming
          only from_date+window isn't covered — i.e. return the newest possible
          (today) so the backfill re-pulls the whole window from scratch.
        """
        if not stats.get("truncated") or not self.DATE_FILTER_FIELD:
            return from_date

        dates = [
            d for d in (
                getattr(row, self.DATE_FILTER_FIELD, None) for row in validated
            ) if d is not None
        ]
        if dates:
            return min(dates)

        # Truncated but couldn't read any record date — don't claim coverage we
        # can't prove. Record today so the backward backfill re-fetches the
        # whole window rather than silently skipping it.
        return date.today()

    def _touch_backfill_state(self, conn, company_id: str, from_date: date) -> None:
        """
        Record how far back this pipeline has now fetched.

        Upserts tz_backfill_state.oldest_fetched_date to the EARLIER of the
        existing value and `from_date`, so the watermark only ever moves
        backwards in time. Called automatically on every successful run().
        """
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tz_backfill_state
                       (company_id, pipeline_name, oldest_fetched_date, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (company_id, pipeline_name) DO UPDATE SET
                    oldest_fetched_date = LEAST(
                        tz_backfill_state.oldest_fetched_date, EXCLUDED.oldest_fetched_date
                    ),
                    updated_at = NOW()
                """,
                (company_id, self.PIPELINE_NAME, from_date),
            )
        conn.commit()

    @classmethod
    def get_oldest_fetched_date(cls, conn, company_id: str = "kbrushes") -> date | None:
        """Earliest date this pipeline has data for, or None if never run."""
        with conn.cursor() as cur:
            cur.execute(
                """SELECT oldest_fetched_date FROM tz_backfill_state
                    WHERE company_id = %s AND pipeline_name = %s""",
                (company_id, cls.PIPELINE_NAME),
            )
            row = cur.fetchone()
        if row and row[0]:
            return row[0].date() if hasattr(row[0], "date") else row[0]
        return None

    @classmethod
    def get_backfill_floor(cls, conn, company_id: str = "kbrushes") -> date | None:
        """Per-pipeline floor date (stop backfilling past this), or None."""
        with conn.cursor() as cur:
            cur.execute(
                """SELECT floor_date FROM tz_backfill_state
                    WHERE company_id = %s AND pipeline_name = %s""",
                (company_id, cls.PIPELINE_NAME),
            )
            row = cur.fetchone()
        if row and row[0]:
            return row[0].date() if hasattr(row[0], "date") else row[0]
        return None

    # ── Abstract methods (subclasses implement these) ─────────────────────────

    @abstractmethod
    def _get_filters(self, from_date: str, to_date: str) -> dict:
        """Return the filters dict for fetch_report()."""
        ...

    @abstractmethod
    def _upsert(self, conn, rows: list, company_id: str) -> int:
        """Insert/update rows into the cached table, tagged with company_id
        (the brand the data belongs to). Return count of rows upserted."""
        ...
