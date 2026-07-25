"""Zoho Books → zb_invoices. Invoice HEADERS (list endpoint) — includes live
balance (real AR) and paid dates, which TranzAct never gave us."""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

import psycopg2.extras
from pydantic import BaseModel, model_validator

from vinayak.pipelines.zoho.base import ZohoBasePipeline


class ZohoInvoiceRow(BaseModel):
    zoho_id: str
    invoice_number: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = None
    invoice_date: Optional[date] = None
    due_date: Optional[date] = None
    status: Optional[str] = None
    sub_total: Optional[float] = None
    tax_total: Optional[float] = None
    total: Optional[float] = None
    balance: Optional[float] = None
    last_payment_date: Optional[date] = None
    raw: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def remap(cls, d: Any):
        if not isinstance(d, dict):
            return d
        return {
            "zoho_id": str(d.get("invoice_id", "")),
            "invoice_number": d.get("invoice_number"),
            "customer_id": str(d.get("customer_id") or "") or None,
            "customer_name": d.get("customer_name"),
            "invoice_date": d.get("date") or None,
            "due_date": d.get("due_date") or None,
            "status": d.get("status"),
            "sub_total": d.get("sub_total"),
            "tax_total": d.get("tax_total"),
            "total": d.get("total"),
            "balance": d.get("balance"),
            "last_payment_date": d.get("last_payment_date") or None,
            "raw": d,
        }


class ZohoInvoicesPipeline(ZohoBasePipeline):
    PIPELINE_NAME = "zoho_invoices"
    RESOURCE = "invoices"
    LIST_KEY = "invoices"
    TABLE_NAME = "zb_invoices"
    RowSchema = ZohoInvoiceRow

    def _upsert(self, conn, rows: list[ZohoInvoiceRow], company_id: str) -> int:
        if not rows:
            return 0
        records = [(company_id, r.zoho_id, r.invoice_number, r.customer_id,
                    r.customer_name, r.invoice_date, r.due_date, r.status,
                    r.sub_total, r.tax_total, r.total, r.balance,
                    r.last_payment_date, self._raw_json(r)) for r in rows]
        sql = """
            INSERT INTO zb_invoices (company_id, zoho_id, invoice_number, customer_id,
                customer_name, invoice_date, due_date, status, sub_total, tax_total,
                total, balance, last_payment_date, raw)
            VALUES %s
            ON CONFLICT (company_id, zoho_id) DO UPDATE SET
                invoice_number=EXCLUDED.invoice_number, customer_id=EXCLUDED.customer_id,
                customer_name=EXCLUDED.customer_name, invoice_date=EXCLUDED.invoice_date,
                due_date=EXCLUDED.due_date, status=EXCLUDED.status,
                sub_total=EXCLUDED.sub_total, tax_total=EXCLUDED.tax_total,
                total=EXCLUDED.total, balance=EXCLUDED.balance,
                last_payment_date=EXCLUDED.last_payment_date, raw=EXCLUDED.raw,
                fetched_at=NOW()
        """
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500,
                                           template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)")
        conn.commit()
        return len(records)
