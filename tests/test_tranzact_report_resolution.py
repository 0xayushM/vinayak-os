"""
TranzAct Aug-2026 re-keying: legacy numeric report ids resolve, via the
account's report catalog, to the live per-company UUIDs — with no network.
"""
import pytest

from vinayak.adapters.tranzact import client as C
from vinayak.adapters.tranzact.reports import REPORT_IDS, REPORT_FUNCTIONS, LEGACY_ID_TO_FUNCTION


def setup_function():
    C._catalog_cache.clear()


def _creds():
    return C.TranzactCreds(email="a@b.com", password="x", base_url="https://be.example")


def _fake_catalog(monkeypatch, catalog):
    calls = {"n": 0}
    def fake(creds, force=False):
        calls["n"] += 1
        return catalog
    monkeypatch.setattr(C, "_report_catalog", fake)
    return calls


def test_every_pipeline_has_a_function_name_and_legacy_map_is_consistent():
    assert set(REPORT_FUNCTIONS) == set(REPORT_IDS)
    for name, legacy in REPORT_IDS.items():
        assert LEGACY_ID_TO_FUNCTION[legacy] == REPORT_FUNCTIONS[name]


def test_legacy_numeric_id_resolves_to_uuid(monkeypatch):
    uuid = "019fa0df-0c00-89aa-84ec-0000000f422f"
    _fake_catalog(monkeypatch, {"sales_invoice_item_register": uuid})
    assert C.resolve_report_id(_creds(), "29") == uuid          # legacy sales_invoices id


def test_function_name_resolves_directly(monkeypatch):
    uuid = "019fa0df-0c00-89aa-84ec-0000000f422f"
    _fake_catalog(monkeypatch, {"po_report": uuid})
    assert C.resolve_report_id(_creds(), "po_report") == uuid


def test_uuid_passes_through_without_catalog(monkeypatch):
    calls = _fake_catalog(monkeypatch, {})
    uuid = "019fa0df-0c00-89aa-84ec-0000000f422f"
    assert C.resolve_report_id(_creds(), uuid) == uuid
    assert calls["n"] == 0                                        # never fetched


def test_unknown_report_gives_clear_error_after_one_refetch(monkeypatch):
    calls = _fake_catalog(monkeypatch, {"something_else": "019fa0df-0c00-89aa-84ec-000000000001"})
    with pytest.raises(RuntimeError, match="not found in this account's catalog"):
        C.resolve_report_id(_creds(), "29")
    assert calls["n"] == 2                                        # initial + one forced refetch
