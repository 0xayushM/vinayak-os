"""Zoho Books → zb_items. Item master with stock on hand AND purchase_rate
(cost) — which finally enables real margin computation for Zoho workspaces."""
from __future__ import annotations

from typing import Any, Optional

import psycopg2.extras
from pydantic import BaseModel, model_validator

from vinayak.pipelines.zoho.base import ZohoBasePipeline


class ZohoItemRow(BaseModel):
    zoho_id: str
    item_name: Optional[str] = None
    sku: Optional[str] = None
    category: Optional[str] = None
    rate: Optional[float] = None
    purchase_rate: Optional[float] = None
    stock_on_hand: Optional[float] = None
    unit: Optional[str] = None
    status: Optional[str] = None
    raw: Optional[dict] = None

    @model_validator(mode="before")
    @classmethod
    def remap(cls, d: Any):
        if not isinstance(d, dict):
            return d
        return {
            "zoho_id": str(d.get("item_id", "")),
            "item_name": d.get("name") or d.get("item_name"),
            "sku": d.get("sku") or None,
            "category": (d.get("group_name") or d.get("category_name")) or None,
            "rate": d.get("rate"),
            "purchase_rate": d.get("purchase_rate"),
            "stock_on_hand": d.get("stock_on_hand") or d.get("available_stock"),
            "unit": d.get("unit"),
            "status": d.get("status"),
            "raw": d,
        }


class ZohoItemsPipeline(ZohoBasePipeline):
    PIPELINE_NAME = "zoho_items"
    RESOURCE = "items"
    LIST_KEY = "items"
    TABLE_NAME = "zb_items"
    RowSchema = ZohoItemRow

    def _upsert(self, conn, rows: list[ZohoItemRow], company_id: str) -> int:
        if not rows:
            return 0
        records = [(company_id, r.zoho_id, r.item_name, r.sku, r.category, r.rate,
                    r.purchase_rate, r.stock_on_hand, r.unit, r.status,
                    self._raw_json(r)) for r in rows]
        sql = """
            INSERT INTO zb_items (company_id, zoho_id, item_name, sku, category,
                rate, purchase_rate, stock_on_hand, unit, status, raw)
            VALUES %s
            ON CONFLICT (company_id, zoho_id) DO UPDATE SET
                item_name=EXCLUDED.item_name, sku=EXCLUDED.sku,
                category=EXCLUDED.category, rate=EXCLUDED.rate,
                purchase_rate=EXCLUDED.purchase_rate,
                stock_on_hand=EXCLUDED.stock_on_hand, unit=EXCLUDED.unit,
                status=EXCLUDED.status, raw=EXCLUDED.raw, fetched_at=NOW()
        """
        with conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, sql, records, page_size=500,
                                           template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)")
        conn.commit()
        return len(records)
