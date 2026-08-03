"""
Unit tests for the canonical GRN/QIR mapping — behind the GRN panel once it reads
canon_grn_flat.

The one rule that must not break: rejected_qty is NULL when a received line has
not yet been inspected, and pending_qir counts those NULLs. The mapper must
PRESERVE the None rather than collapsing it to 0.
"""
from datetime import date

from vinayak.canonical.tranzact_canonical import grn_fields


def _fields(**over):
    base = dict(
        raw_id="rid-1", grn_number="GRN-1", grn_date=date(2026, 1, 1),
        vendor_code="V1", vendor_name="Acme Supplies", po_number="PO-1",
        item_code="ITEM-A", item_name="Widget A",
        ordered_qty=100, received_qty=100, rejected_qty=5, accepted_qty=95,
    )
    base.update(over)
    return grn_fields(**base)


def test_source_ref_is_the_raw_id():
    assert _fields(raw_id="hash-grn")["source_ref"] == "hash-grn"


def test_uninspected_rejected_qty_stays_none():
    # received but not yet inspected → rejected_qty must remain None (pending QIR)
    f = _fields(rejected_qty=None)
    assert f["rejected_qty"] is None
    assert f["received_qty"] == 100.0


def test_inspected_quantities_are_floats():
    f = _fields(rejected_qty=5, accepted_qty=95)
    assert f["rejected_qty"] == 5.0
    assert f["accepted_qty"] == 95.0
    assert isinstance(f["rejected_qty"], float)


def test_passthrough_fields():
    f = _fields()
    assert f["grn_number"] == "GRN-1"
    assert f["po_number"] == "PO-1"
    assert f["vendor_ref"] == "V1"
    assert f["item_code"] == "ITEM-A"
