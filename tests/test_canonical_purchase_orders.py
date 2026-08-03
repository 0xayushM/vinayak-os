"""
Unit tests for the canonical purchase-order mapping — the transformation behind
the Open POs / Overdue POs panels once they read canon_purchase_order_flat.

POs are line-grain with a per-line po_value and no tax basis, so the mapping is a
straight passthrough keyed on the source raw_id (guaranteeing a 1:1 mapping with
tz_purchase_orders, so COUNT(*) and SUM(po_value) reconcile exactly). The only
logic worth pinning down is numeric coercion and that the key is the raw_id.
"""
from datetime import date

from vinayak.canonical.tranzact_canonical import purchase_order_fields


def _fields(**over):
    base = dict(
        raw_id="rid-1", po_number="PO-1", po_date=date(2026, 1, 1),
        vendor_code="V1", vendor_name="Acme Supplies",
        item_code="ITEM-A", item_name="Widget A",
        ordered_qty=100, received_qty=40, pending_qty=60,
        po_value=50000, expected_date=date(2026, 2, 1), status="Open",
    )
    base.update(over)
    return purchase_order_fields(**base)


def test_source_ref_is_the_raw_id():
    f = _fields(raw_id="content-hash-xyz")
    assert f["source_ref"] == "content-hash-xyz"  # 1:1 with the tz row


def test_fields_pass_through():
    f = _fields()
    assert f["po_number"] == "PO-1"
    assert f["vendor_ref"] == "V1"
    assert f["vendor_name"] == "Acme Supplies"
    assert f["item_code"] == "ITEM-A"
    assert f["status"] == "Open"
    assert f["expected_date"] == date(2026, 2, 1)


def test_numeric_coercion():
    f = _fields(ordered_qty=None, received_qty=None, pending_qty=None, po_value=None)
    assert f["ordered_qty"] == 0.0
    assert f["received_qty"] == 0.0
    assert f["pending_qty"] == 0.0
    assert f["po_value"] == 0.0


def test_po_value_is_float():
    f = _fields(po_value="75000")
    assert f["po_value"] == 75000.0
    assert isinstance(f["po_value"], float)
