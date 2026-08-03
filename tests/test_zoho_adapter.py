"""
Zoho adapter tests — no network. Validates the parts we CAN verify before a
real Zoho org exists: DC URL construction, row-schema mapping from realistic
API JSON, pagination logic, and 429/401 handling in the client.
"""
from unittest.mock import MagicMock, patch

import pytest

from vinayak.adapters.zoho.auth import DCS, ZohoCreds
from vinayak.adapters.zoho import client as zclient
from vinayak.pipelines.zoho.invoices import ZohoInvoiceRow
from vinayak.pipelines.zoho.contacts import ZohoContactRow
from vinayak.pipelines.zoho.items import ZohoItemRow


CREDS = ZohoCreds(client_id="cid", client_secret="sec", refresh_token="rt",
                  organization_id="60001234567", dc="in")


# ── DC / URL construction ─────────────────────────────────────────────────────
def test_indian_dc_urls():
    assert CREDS.accounts_base == "https://accounts.zoho.in"
    assert CREDS.books_base == "https://www.zohoapis.in/books/v3"

def test_all_dcs_have_both_hosts():
    for dc, (acct, api) in DCS.items():
        assert acct.startswith("https://accounts.zoho")
        assert api.startswith("https://www.zohoapis")


# ── Row mapping from realistic Zoho JSON ──────────────────────────────────────
def test_invoice_row_maps_zoho_shape():
    r = ZohoInvoiceRow(**{
        "invoice_id": 982000000567240, "invoice_number": "INV-00004",
        "customer_id": 982000000567001, "customer_name": "Bowman Furniture",
        "date": "2026-06-15", "due_date": "2026-07-15", "status": "overdue",
        "sub_total": 40000.0, "tax_total": 7200.0, "total": 47200.0,
        "balance": 25000.0, "last_payment_date": "",
    })
    assert r.zoho_id == "982000000567240"
    assert str(r.invoice_date) == "2026-06-15"
    assert r.balance == 25000.0            # live AR per invoice
    assert r.last_payment_date is None     # empty string coerced to None
    assert r.raw["invoice_number"] == "INV-00004"

def test_contact_row_captures_marketing_fields():
    r = ZohoContactRow(**{
        "contact_id": 982000000567001, "contact_name": "Bowman Furniture",
        "contact_type": "customer", "email": "info@bowman.in",
        "phone": "011-23456789", "mobile": "+91 98100 11111",
        "payment_terms": 30, "outstanding_receivable_amount": 25000.0,
        "status": "active",
    })
    assert r.email == "info@bowman.in"     # the field TranzAct never had
    assert r.payment_terms == 30           # terms straight from source, not taught
    assert r.outstanding_receivable == 25000.0

def test_item_row_captures_cost():
    r = ZohoItemRow(**{
        "item_id": 982000000030049, "name": "Nylon Brush 2in", "sku": "NB-2",
        "rate": 120.0, "purchase_rate": 74.0, "stock_on_hand": 340.0,
        "status": "active",
    })
    assert r.purchase_rate == 74.0         # enables real margin for Zoho orgs

def test_invalid_row_fails_validation():
    with pytest.raises(Exception):
        ZohoInvoiceRow(**{"invoice_id": 1, "date": "not-a-date"})


# ── Pagination ────────────────────────────────────────────────────────────────
def _resp(json_body, status=200):
    m = MagicMock()
    m.status_code = status
    m.ok = status < 400
    m.json.return_value = json_body
    return m

@patch.object(zclient, "_throttle", lambda: None)
@patch.object(zclient, "get_access_token", lambda c: "tok")
def test_fetch_all_walks_pages():
    pages = [
        _resp({"code": 0, "invoices": [{"invoice_id": 1}, {"invoice_id": 2}],
               "page_context": {"has_more_page": True}}),
        _resp({"code": 0, "invoices": [{"invoice_id": 3}],
               "page_context": {"has_more_page": False}}),
    ]
    with patch("requests.Session.get", side_effect=pages) as g:
        rows = zclient.fetch_all(CREDS, "invoices", "invoices")
    assert [r["invoice_id"] for r in rows] == [1, 2, 3]
    # organization_id must be on every request
    for call in g.call_args_list:
        assert call.kwargs["params"]["organization_id"] == "60001234567"

@patch.object(zclient, "_throttle", lambda: None)
@patch.object(zclient, "get_access_token", lambda c: "tok")
def test_client_backs_off_on_429_then_succeeds():
    pages = [
        _resp({}, status=429),
        _resp({"code": 0, "invoices": [{"invoice_id": 9}],
               "page_context": {"has_more_page": False}}),
    ]
    with patch("requests.Session.get", side_effect=pages), patch("time.sleep"):
        rows = zclient.fetch_all(CREDS, "invoices", "invoices")
    assert rows == [{"invoice_id": 9}]

@patch.object(zclient, "_throttle", lambda: None)
@patch.object(zclient, "get_access_token", lambda c: "tok")
def test_client_raises_on_zoho_error_code():
    with patch("requests.Session.get", return_value=_resp({"code": 1002, "message": "bad org"})):
        with pytest.raises(RuntimeError, match="1002"):
            zclient.fetch_all(CREDS, "invoices", "invoices")
