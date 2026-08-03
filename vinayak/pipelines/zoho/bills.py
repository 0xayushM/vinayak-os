"""Zoho Books → zb_bills. Vendor bills (accounts payable) — purchases + live AP."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

import psycopg2.extras
from pydantic import BaseModel, model_validator

from vinayak.pipelines.zoho.base import ZohoBasePipeline


class ZohoBillRow(BaseModel):
    zoho_id: str
    bill_number: Optional[str] = None
    vendor_id: Optional[str] = None
    vendor_name: Optional[str] = None
    bill_date: Optional[date] = None
    due_date: Optional[date] = None
    status: Optional[str] = None
    sub_total: Optional[float] = None
    total: Optional[float] = None
    balance: Optional[float] = None
    raw: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def remap(cls, d: Any):
        if not isinstance(d, dict):
            return d
        return {
            "zoho_id": str(d.get("bill_id", "")),
            "bill_number": d.get("bill_number"),
            "vendor_id": str(d.get("vendor_id") or "") or None,
            "vendor_name": d.get("vendor_name"),
            "bill_date": d.get("date") or None,
            "due_date": d.get("due_date") or None,
            "status": d.get("status"),
            "sub_total": d.get("sub_total"),
            "total": d.get("total"),
            "balance": d.get("balance"),
            "raw": d,
        }


class ZohoBillsPipeline(ZohoBasePipeline):
    PIPELINE_NAME = "zoho_bills"
    RESOURCE = "bills"
    LIST_KEY = "bills"
    TABLE_NAME = "zb_bills"
    RowSchema = ZohoBillRow

    def _upsert(self, conn, rows: list[ZohoBillRow], company_id: str) -> int:
        if not rows:
            return 0
        records = [(company_id, r.zoho_id, r.bill_number, r.vendor_id, r.vendor_name,
                    r.bill_date, r.due_date, r.status, r.sub_total, r.total,
                    r.balance, self._raw_json(r)) for r in rows]
        sql = """
            INSERT INTO zb_bills (company_id, zoho_id, bill_number, vendor_id,
                vendor_name, bill_date, due_date, status, sub_total, total, balance, raw)
            VALUES %s
            ON CONFLICT (company_id, zoho_id) DO UPDATE SET
                bill_number=EXCLUDED.bill_number, vendor_id=EXCLUDED.vendor_id,
                vendor_name=EXCLUDED.vendor_name, bill_date=EXCLUDED.bill_date,
                due_date=EXCLUDED.due_date, status=EXCLUDED.status,
                sub_total=EXCLUDED.sub_total, total=EXCLUDED.total,
                balance=EXCLUDED.balance, raw=EXCLUDED.raw, fetched_at=NOW()
        """
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500,
                                           template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)")
        conn.commit()
        return len(records)
