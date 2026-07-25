"""
Unit tests for the canonical sales-quotation mapping — behind the Quote Pipeline
panel once it reads canon_sales_quotation_flat.

Line-grain, keyed on the source raw_id. The only logic worth pinning: numeric
coercion and that converted_to_order becomes a real bool (it drives the
won/open funnel filters).
"""
from datetime import date

from vinayak.canonical.tranzact_canonical import sales_quotation_fields


def _fields(**over):
    base = dict(
        raw_id="rid-1", quote_number="Q-1", quote_date=date(2026, 1, 1),
        customer_code="C1", customer_name="Dev Colour",
        sku_code="SKU-A", sku_name="Brush A",
        quoted_qty=100, quoted_value=90000, status="Open",
        valid_until=date(2026, 3, 1), converted_to_order=False,
    )
    base.update(over)
    return sales_quotation_fields(**base)


def test_source_ref_is_the_raw_id():
    assert _fields(raw_id="hash-q")["source_ref"] == "hash-q"


def test_fields_pass_through():
    f = _fields()
    assert f["quote_number"] == "Q-1"
    assert f["customer_ref"] == "C1"
    assert f["status"] == "Open"
    assert f["valid_until"] == date(2026, 3, 1)


def test_numeric_coercion():
    f = _fields(quoted_qty=None, quoted_value=None)
    assert f["quoted_qty"] == 0.0
    assert f["quoted_value"] == 0.0


def test_converted_flag_is_real_bool():
    assert _fields(converted_to_order=True)["converted_to_order"] is True
    assert _fields(converted_to_order=None)["converted_to_order"] is False
    assert _fields(converted_to_order=1)["converted_to_order"] is True
