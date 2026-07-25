"""Zoho Books → zb_contacts. Customers AND vendors, WITH email/phone —
the contact data TranzAct never had (feeds marketing's customer_contacts)."""
from __future__ import annotations

from typing import Any, Optional

import psycopg2.extras
from pydantic import BaseModel, model_validator

from vinayak.pipelines.zoho.base import ZohoBasePipeline


class ZohoContactRow(BaseModel):
    zoho_id: str
    contact_name: Optional[str] = None
    contact_type: Optional[str] = None            # customer | vendor
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    gst_no: Optional[str] = None
    payment_terms: Optional[int] = None
    outstanding_receivable: Optional[float] = None
    outstanding_payable: Optional[float] = None
    status: Optional[str] = None
    raw: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def remap(cls, d: Any):
        if not isinstance(d, dict):
            return d
        return {
            "zoho_id": str(d.get("contact_id", "")),
            "contact_name": d.get("contact_name"),
            "contact_type": d.get("contact_type"),
            "company_name": d.get("company_name"),
            "email": d.get("email") or None,
            "phone": d.get("phone") or None,
            "mobile": d.get("mobile") or None,
            "gst_no": d.get("gst_no"),
            "payment_terms": d.get("payment_terms"),
            "outstanding_receivable": d.get("outstanding_receivable_amount"),
            "outstanding_payable": d.get("outstanding_payable_amount"),
            "status": d.get("status"),
            "raw": d,
        }


class ZohoContactsPipeline(ZohoBasePipeline):
    PIPELINE_NAME = "zoho_contacts"
    RESOURCE = "contacts"
    LIST_KEY = "contacts"
    TABLE_NAME = "zb_contacts"
    RowSchema = ZohoContactRow

    def _upsert(self, conn, rows: list[ZohoContactRow], company_id: str) -> int:
        if not rows:
            return 0
        records = [(company_id, r.zoho_id, r.contact_name, r.contact_type,
                    r.company_name, r.email, r.phone, r.mobile, r.gst_no,
                    r.payment_terms, r.outstanding_receivable, r.outstanding_payable,
                    r.status, self._raw_json(r)) for r in rows]
        sql = """
            INSERT INTO zb_contacts (company_id, zoho_id, contact_name, contact_type,
                company_name, email, phone, mobile, gst_no, payment_terms,
                outstanding_receivable, outstanding_payable, status, raw)
            VALUES %s
            ON CONFLICT (company_id, zoho_id) DO UPDATE SET
                contact_name=EXCLUDED.contact_name, contact_type=EXCLUDED.contact_type,
                company_name=EXCLUDED.company_name, email=EXCLUDED.email,
                phone=EXCLUDED.phone, mobile=EXCLUDED.mobile, gst_no=EXCLUDED.gst_no,
                payment_terms=EXCLUDED.payment_terms,
                outstanding_receivable=EXCLUDED.outstanding_receivable,
                outstanding_payable=EXCLUDED.outstanding_payable,
                status=EXCLUDED.status, raw=EXCLUDED.raw, fetched_at=NOW()
        """
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500,
                                           template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)")
        conn.commit()
        return len(records)
