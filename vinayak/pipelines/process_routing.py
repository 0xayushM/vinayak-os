"""
pipelines/process_routing.py
─────────────────────────────
Pulls TranzAct report 86 (Process Routing) and caches the result in
tz_process_routing.

Dashboard panels fed:
  - SKU-level process routing map (sequence of operations)
  - Standard hours per process and per SKU
  - Machine centre utilisation benchmarks
  - Routing complexity analysis (number of process steps per SKU)
  - Process bottleneck identification
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import psycopg2.extras
from pydantic import BaseModel, field_validator, model_validator

from vinayak.pipelines.base import BasePipeline
from vinayak.pipelines.helpers import stable_row_id

logger = logging.getLogger(__name__)

# ── Row schema ────────────────────────────────────────────────────────────────

class ProcessRoutingRow(BaseModel):
    raw_id: str
    sku_code: Optional[str] = None
    sku_name: Optional[str] = None
    process_name: Optional[str] = None
    sequence_number: Optional[int] = None
    standard_hours: Optional[float] = None
    machine_centre: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def remap_api_fields(cls, data):
        if not isinstance(data, dict):
            return data
        mapped = {
            "sku_code":        data.get("itemid"),
            "sku_name":        data.get("fg_name"),
            "process_name":    data.get("full_routing_name"),
            "sequence_number": None,
            "standard_hours":  None,
            "machine_centre":  None,
        }
        # Stable content-hash id (not the volatile uuid) — prevents re-sync dupes.
        mapped["raw_id"] = stable_row_id(mapped["sku_code"], mapped["process_name"])
        return mapped

    @field_validator("sequence_number", mode="before")
    @classmethod
    def coerce_int(cls, v):
        if v is None or v == "":
            return None
        try:
            return int(v)
        except (ValueError, TypeError):
            return None

# ── Pipeline ──────────────────────────────────────────────────────────────────

class ProcessRoutingPipeline(BasePipeline):
    PIPELINE_NAME = "process_routing"
    REPORT_ID = "86"
    TABLE_NAME = "tz_process_routing"
    RowSchema = ProcessRoutingRow

    def _upsert(self, conn, rows: list[ProcessRoutingRow], company_id: str) -> int:
        if not rows:
            return 0

        records = [
            (
                company_id,
                r.raw_id,
                r.sku_code,
                r.sku_name,
                r.process_name,
                r.sequence_number,
                r.standard_hours,
                r.machine_centre,
            )
            for r in rows
        ]

        sql = """
            INSERT INTO tz_process_routing (
                company_id, raw_id, sku_code, sku_name, process_name,
                sequence_number, standard_hours, machine_centre
            ) VALUES %s
            ON CONFLICT (company_id, raw_id) DO UPDATE SET
                sku_code        = EXCLUDED.sku_code,
                sku_name        = EXCLUDED.sku_name,
                process_name    = EXCLUDED.process_name,
                sequence_number = EXCLUDED.sequence_number,
                standard_hours  = EXCLUDED.standard_hours,
                machine_centre  = EXCLUDED.machine_centre,
                fetched_at      = NOW()
        """

        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500)
            row_count = cur.rowcount
        conn.commit()
        return row_count
