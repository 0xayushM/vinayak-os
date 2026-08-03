"""
Unit tests for the canonical purchase-invoice mapping — the transformation that
feeds the Purchases panels once they read canon_purchase_invoice_flat.

The risky logic is the tax rule: TranzAct's line value (item_total_value) is
TAX-INCLUSIVE, so the canonical line_total must be stored EX-TAX (line_incl - tax),
exactly like the sales side. The source_ref must be deterministic so a rebuild
updates rows in place instead of duplicating.
"""
from vinayak.canonical.tranzact_canonical import purchase_line_fields


def test_line_total_is_stored_ex_tax():
    # line incl-tax 1180, tax 180  →  ex-tax goods value 1000
    f = purchase_line_fields("PINV-1", "ITEM-A", "Widget A",
                             qty=10, unit_price=118, line_incl=1180, tax=180)
    assert f["line_total"] == 1000.0
    assert f["quantity"] == 10.0
    assert f["unit_price"] == 118.0
    assert f["sku"] == "ITEM-A"
    assert f["sku_name"] == "Widget A"
    assert f["invoice_number"] == "PINV-1"


def test_zero_tax_leaves_line_total_unchanged():
    f = purchase_line_fields("PINV-2", "ITEM-B", "Widget B",
                             qty=1, unit_price=500, line_incl=500, tax=0)
    assert f["line_total"] == 500.0


def test_none_values_coerce_to_zero():
    f = purchase_line_fields("PINV-3", "ITEM-C", None,
                             qty=None, unit_price=None, line_incl=None, tax=None)
    assert f["line_total"] == 0.0
    assert f["quantity"] == 0.0
    assert f["unit_price"] == 0.0


def test_source_ref_is_deterministic():
    a = purchase_line_fields("PINV-4", "ITEM-D", "D", 2, 50, 118, 18)
    b = purchase_line_fields("PINV-4", "ITEM-D", "D", 2, 50, 118, 18)
    assert a["source_ref"] == b["source_ref"]  # same line → same upsert key


def test_source_ref_keys_on_incl_tax_value():
    # Two lines that differ only by their raw (incl-tax) line value must get
    # different keys — the key is built from the raw value, not the ex-tax one.
    a = purchase_line_fields("PINV-5", "ITEM-E", "E", 1, 100, 118, 18)
    b = purchase_line_fields("PINV-5", "ITEM-E", "E", 1, 100, 236, 36)
    assert a["source_ref"] != b["source_ref"]
