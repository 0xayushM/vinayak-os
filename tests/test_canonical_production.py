"""
Unit tests for the canonical production + routing mapping — behind the
Production, WIP, and BOM-coverage panels once they read canon_production_flat /
canon_routing_flat.

Both line-grain, keyed on the source raw_id. Production quantities preserve None
so the ‘completed’ test (planned_qty > 0 AND produced_qty >= planned_qty) and WIP
counts behave exactly as on the raw table.
"""
from datetime import date

from vinayak.canonical.tranzact_canonical import production_fields, routing_fields


def _prod(**over):
    base = dict(
        raw_id="rid-1", production_date=date(2026, 1, 1), work_order_number="WO-1",
        sku_code="SKU-A", sku_name="Brush A", process_name="Moulding",
        planned_qty=100, produced_qty=80, rejected_qty=2, status="WIP",
    )
    base.update(over)
    return production_fields(**base)


def test_production_source_ref_is_raw_id():
    assert _prod(raw_id="hash-p")["source_ref"] == "hash-p"


def test_production_preserves_null_quantities():
    f = _prod(planned_qty=None, produced_qty=None, rejected_qty=None)
    assert f["planned_qty"] is None
    assert f["produced_qty"] is None
    assert f["rejected_qty"] is None


def test_production_quantities_float_when_present():
    f = _prod(planned_qty=100, produced_qty=80)
    assert f["planned_qty"] == 100.0
    assert f["produced_qty"] == 80.0
    assert f["status"] == "WIP"


def test_routing_source_ref_and_passthrough():
    f = routing_fields("hash-r", "SKU-A", "Brush A", "Moulding", 1, 2.5, "MC-01")
    assert f["source_ref"] == "hash-r"
    assert f["sku_code"] == "SKU-A"
    assert f["sequence_number"] == 1
    assert f["standard_hours"] == 2.5
    assert f["machine_centre"] == "MC-01"


def test_routing_null_coercion():
    f = routing_fields("hash-r", "SKU-A", "Brush A", "Moulding", None, None, None)
    assert f["sequence_number"] is None
    assert f["standard_hours"] is None
