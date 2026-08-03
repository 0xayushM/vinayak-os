"""
Unit tests for the canonical sales-order mapping — behind the Order Book /
Overdue Orders panels once they read canon_sales_order_flat.

Line-grain with a per-line order_value and no tax basis, keyed on the source
raw_id for an exact 1:1 mapping with tz_sales_orders (so COUNT(*),
SUM(order_value) and dispatched_pct reconcile by construction).
"""
from datetime import date

from vinayak.canonical.tranzact_canonical import sales_order_fields


def _fields(**over):
    base = dict(
        raw_id="rid-1", order_number="SO-1", order_date=date(2026, 1, 1),
        customer_code="C1", customer_name="Dev Colour",
        sku_code="SKU-A", sku_name="Brush A",
        ordered_qty=100, dispatched_qty=30, pending_qty=70,
        order_value=80000, delivery_date=date(2026, 2, 1), status="Open",
    )
    base.update(over)
    return sales_order_fields(**base)


def test_source_ref_is_the_raw_id():
    f = _fields(raw_id="content-hash-abc")
    assert f["source_ref"] == "content-hash-abc"


def test_fields_pass_through():
    f = _fields()
    assert f["order_number"] == "SO-1"
    assert f["customer_ref"] == "C1"
    assert f["customer_name"] == "Dev Colour"
    assert f["sku_code"] == "SKU-A"
    assert f["status"] == "Open"
    assert f["delivery_date"] == date(2026, 2, 1)


def test_numeric_coercion():
    f = _fields(ordered_qty=None, dispatched_qty=None, pending_qty=None, order_value=None)
    assert f["ordered_qty"] == 0.0
    assert f["dispatched_qty"] == 0.0
    assert f["pending_qty"] == 0.0
    assert f["order_value"] == 0.0


def test_order_value_is_float():
    f = _fields(order_value="80000")
    assert f["order_value"] == 80000.0
    assert isinstance(f["order_value"], float)
