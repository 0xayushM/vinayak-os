"""
pipelines/zoho/base.py
───────────────────────
ZohoBasePipeline — the Zoho twin of pipelines/base.BasePipeline, deliberately
NOT inheriting it (that class is coupled to the TranzAct client). Same safety
contract: fetch → validate (Pydantic, bad rows skipped) → upsert in place →
log to tz_sync_runs. Never truncate; a failed sync leaves old data standing.

Differences from the TranzAct base, courtesy of a saner API:
  • upsert keys on Zoho's own stable IDs — no content-hash workaround
  • no page-cursor machinery — fetch_all() walks real pagination
  • raw JSON kept per row (raw column) so we can re-map without re-fetching
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod

import psycopg2
import psycopg2.extras

from vinayak.adapters.zoho.auth import ZohoCreds
from vinayak.adapters.zoho.client import fetch_all
from vinayak.config import DATABASE_URL

logger = logging.getLogger(__name__)


class ZohoBasePipeline(ABC):
    PIPELINE_NAME: str          # e.g. "zoho_invoices" (tz_sync_runs.pipeline_name)
    RESOURCE: str               # Zoho endpoint, e.g. "invoices"
    LIST_KEY: str               # key of the row list in the response
    TABLE_NAME: str             # zb_* table
    RowSchema: type             # Pydantic model

    LIST_PARAMS: dict = {}      # extra query params for the list call

    def run(self, company_id: str, creds: ZohoCreds) -> dict:
        conn = psycopg2.connect(DATABASE_URL)
        run_id = self._start_run(conn, company_id)
        try:
            raw = fetch_all(creds, self.RESOURCE, self.LIST_KEY, self.LIST_PARAMS)
            validated = self._validate(raw)
            upserted = self._upsert(conn, validated, company_id)
            self._finish_run(conn, run_id, "success", len(raw), upserted)
            logger.info("%s: ✅ fetched=%d upserted=%d (%s)",
                        self.PIPELINE_NAME, len(raw), upserted, company_id)
            return {"rows_fetched": len(raw), "rows_upserted": upserted}
        except Exception as exc:
            self._fail_run(conn, run_id, str(exc))
            logger.exception("%s: ❌ failed (%s)", self.PIPELINE_NAME, company_id)
            raise
        finally:
            conn.close()

    # ── subclass contract ────────────────────────────────────────────────────
    @abstractmethod
    def _upsert(self, conn, rows: list, company_id: str) -> int: ...

    # ── shared plumbing ──────────────────────────────────────────────────────
    def _validate(self, raw_rows: list[dict]) -> list:
        valid, skipped = [], 0
        for row in raw_rows:
            try:
                valid.append(self.RowSchema(**row))
            except Exception as exc:  # noqa: BLE001
                skipped += 1
                logger.debug("%s: skipped invalid row (%s)", self.PIPELINE_NAME, exc)
        if skipped:
            logger.warning("%s: %d/%d rows skipped validation",
                           self.PIPELINE_NAME, skipped, len(raw_rows))
        return valid

    @staticmethod
    def _raw_json(model) -> str:
        return json.dumps(model.raw or {}, default=str)

    def _start_run(self, conn, company_id: str) -> int:
        # Zoho resources are named REST endpoints, not numeric TranzAct report
        # IDs, so report_id is left NULL (see migration 017).
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tz_sync_runs
                       (company_id, pipeline_name, report_id, status, is_backfill)
                   VALUES (%s, %s, NULL, 'running', FALSE) RETURNING id""",
                (company_id, self.PIPELINE_NAME),
            )
            run_id = cur.fetchone()[0]
        conn.commit()
        return run_id

    def _finish_run(self, conn, run_id: int, status: str, fetched: int, upserted: int) -> None:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE tz_sync_runs SET status=%s, completed_at=NOW(),
                          rows_fetched=%s, rows_upserted=%s WHERE id=%s""",
                (status, fetched, upserted, run_id),
            )
        conn.commit()

    def _fail_run(self, conn, run_id: int, error: str) -> None:
        try:
            conn.rollback()
            with conn.cursor() as cur:
                cur.execute(
                    """UPDATE tz_sync_runs SET status='failed', completed_at=NOW(),
                              error_message=%s WHERE id=%s""",
                    (error[:2000], run_id),
                )
            conn.commit()
        except Exception as log_exc:  # noqa: BLE001
            logger.error("could not log zoho pipeline failure: %s", log_exc)
