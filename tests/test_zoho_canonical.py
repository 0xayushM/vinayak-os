"""
Unit tests for the Zoho → canonical mapping. Zoho is a DIFFERENT source shape
(header-level invoices, AR derived from balances), so these tests pin the
transformations that make it land in the same canon_* schema as TranzAct:
  • aging computed from due_date, same bucket boundaries
  • a bill's tax derived as total - sub_total
  • the synthetic invoice line carries the invoice's ex-tax goods value
"""
from datetime import date, timedelta

from vinayak.canonical.zoho_canonical import (
    days_overdue_and_bucket, zoho_invoice_header_fields, zoho_invoice_line_fields,
    zoho_payment_fields, zoho_bill_header_fields, zoho_item_fields,
)

TODAY = date(2026, 7, 1)


def test_aging_buckets_match_tranzact_boundaries():
    assert days_overdue_and_bucket(TODAY + timedelta(days=10), TODAY) == (0, "0-30")
    assert days_overdue_and_bucket(TODAY - timedelta(days=30), TODAY) == (30, "0-30")
    assert days_overdue_and_bucket(TODAY - timedelta(days=31), TODAY) == (31, "31-60")
    assert days_overdue_and_bucket(TODAY - timedelta(days=90), TODAY) == (90, "61-90")
    assert days_overdue_and_bucket(TODAY - timedelta(days=91), TODAY) == (91, "90+")
    assert days_overdue_and_bucket(None, TODAY) == (None, None)


def test_invoice_header_maps_goods_tax_net():
    h = zoho_invoice_header_fields(
        "inv1", "INV-1", date(2026, 6, 1), date(2026, 7, 1),
        "cust1", "Dev Colour", sub_total=1000, tax_total=180, total=1180, status="sent")
    assert h["gross"] == 1000.0   # ex-tax goods
    assert h["tax"] == 180.0
    assert h["net"] == 1180.0     # printed grand total
    assert h["customer_ref"] == "cust1"


def test_synthetic_line_carries_goods_value():
    line = zoho_invoice_line_fields("inv1", "INV-1", sub_total=1000, invoice_id="uuid-1")
    assert line["line_total"] == 1000.0
    assert line["sku"] is None            # Zoho has no line breakdown
    assert line["invoice_id"] == "uuid-1"


def test_payment_derives_outstanding_and_aging():
    p = zoho_payment_fields(
        "inv1", "cust1", "Dev Colour", "INV-1", date(2026, 5, 1),
        date(2026, 5, 31), total=1180, balance=500, today=TODAY)
    assert p["outstanding_amount"] == 500.0
    assert p["invoice_amount"] == 1180.0
    assert p["reconciled"] is False
    assert p["days_overdue"] == 31        # 2026-07-01 minus 2026-05-31
    assert p["aging_bucket"] == "31-60"


def test_fully_paid_invoice_is_reconciled():
    p = zoho_payment_fields("inv2", "c", "n", "INV-2", None, None, total=100, balance=0, today=TODAY)
    assert p["reconciled"] is True


def test_bill_tax_is_total_minus_subtotal():
    b = zoho_bill_header_fields(
        "bill1", "BILL-1", date(2026, 6, 1), date(2026, 7, 1),
        "vend1", "Acme", sub_total=2000, total=2360, status="open")
    assert b["gross"] == 2000.0
    assert b["tax"] == 360.0
    assert b["net"] == 2360.0
    assert b["vendor_ref"] == "vend1"


def test_bill_tax_never_negative():
    b = zoho_bill_header_fields("b", "B", None, None, "v", "V",
                                sub_total=2360, total=2000, status="open")
    assert b["tax"] == 0.0


def test_item_valuation_uses_purchase_rate():
    it = zoho_item_fields("it1", "Brush A", "SKU-A", "Brushes",
                          purchase_rate=40, stock_on_hand=100)
    assert it["unit_cost"] == 40.0
    assert it["quantity"] == 100.0
    assert it["total_value"] == 4000.0
    assert it["is_negative_stock"] is False


def test_item_negative_stock_flag():
    it = zoho_item_fields("it2", "Brush B", "SKU-B", None, purchase_rate=10, stock_on_hand=-5)
    assert it["is_negative_stock"] is True
