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
    _upsert(conn, rows) -> int
        Performs the INSERT … ON CONFLICT DO UPDATE and returns rows upserted.

The run() method provides the full pipeline contract:
    fetch (complete report, no date filter) → validate → upsert → log → errors
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import date

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

    # ── Public methods ────────────────────────────────────────────────────────

    def run(
        self,
        company_id: str = "protegere",
        max_seconds: float | None = None,
        creds: TranzactCreds | None = None,
    ) -> int:
        """
        Run this pipeline once over the COMPLETE report and return rows upserted.

        Convenience wrapper around run_chunk() with start_page=1 and no page
        limit. Used for routine refreshes (scheduler, full sync). For a large
        history, use the cursor-driven chunked migration in the connections
        route instead — see docs/RESUMABLE_SYNC.md.
        """
        return self.run_chunk(
            company_id=company_id, creds=creds,
            start_page=1, max_pages=None, max_seconds=max_seconds,
        )["rows_upserted"]

    def run_chunk(
        self,
        company_id: str = "protegere",
        creds: TranzactCreds | None = None,
        start_page: int = 1,
        max_pages: int | None = None,
        max_seconds: float | None = None,
    ) -> dict:
        """
        Fetch ONE chunk of the report (pages start_page…) and upsert it.

        With start_page=1 and max_pages=None this pulls the complete report.
        Pass max_pages to fetch a bounded slice and resume later from
        last_page + 1 — the basis of resumable migration.

        TranzAct has no server-side date filter, so a chunk is just a page range.
        Upserts are keyed on a content hash, so overlapping/re-fetched rows
        overwrite in place rather than duplicating.

        Returns a stats dict:
          rows_upserted, rows_fetched, last_page, total_items,
          more_available (bool), reached_end (bool), truncated (bool)
        """
        conn = psycopg2.connect(DATABASE_URL)
        run_id = self._start_run(conn, is_backfill=False)
        try:
            stats: dict = {}
            raw_rows = fetch_report(
                self.REPORT_ID, None, max_seconds=max_seconds, stats=stats,
                creds=creds, start_page=start_page, max_pages=max_pages,
            )
            rows_fetched = len(raw_rows)
            validated = self._dedupe(self._validate(raw_rows))
            self._upsert(conn, validated, company_id)
            rows_upserted = len(validated)  # execute_values rowcount unreliable with batching
            self._finish_run(conn, run_id, "success", rows_fetched, rows_upserted)
            logger.info(
                "%s: ✅  pages %d.. fetched=%d upserted=%d more=%s",
                self.PIPELINE_NAME, start_page, rows_fetched, rows_upserted,
                stats.get("more_available"),
            )
            return {
                "rows_upserted": rows_upserted,
                "rows_fetched":  rows_fetched,
                "last_page":     stats.get("last_page", start_page - 1),
                "total_items":   stats.get("total_items", 0),
                "more_available": bool(stats.get("more_available")),
                "reached_end":   bool(stats.get("reached_end")),
                "truncated":     bool(stats.get("truncated")),
            }
        except Exception as exc:
            self._fail_run(conn, run_id, str(exc))
            logger.exception("%s: ❌  chunk failed (start_page=%s)", self.PIPELINE_NAME, start_page)
            raise
        finally:
            conn.close()

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

    def _dedupe(self, rows: list) -> list:
        """
        Collapse rows that share the same content-hash id (raw_id) within this
        batch, last-wins. The DB upsert targets ON CONFLICT (company_id, raw_id);
        if a single batch contained two rows with the same raw_id, Postgres
        raises "ON CONFLICT DO UPDATE command cannot affect row a second time".
        Source reports legitimately repeat identical lines, so we de-dup here.
        Rows without a raw_id are passed through untouched.
        """
        seen: dict[str, object] = {}
        passthrough, collapsed = [], 0
        for r in rows:
            rid = getattr(r, "raw_id", None)
            if not rid:
                passthrough.append(r)
                continue
            if rid in seen:
                collapsed += 1
            seen[rid] = r
        if collapsed:
            logger.info(
                "%s: collapsed %d duplicate row(s) in this batch before upsert",
                self.PIPELINE_NAME, collapsed,
            )
        return list(seen.values()) + passthrough

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

    # ── Abstract methods (subclasses implement these) ─────────────────────────

    @abstractmethod
    def _upsert(self, conn, rows: list, company_id: str) -> int:
        """Insert/update rows into the cached table, tagged with company_id
        (the brand the data belongs to). Return count of rows upserted."""
        ...
