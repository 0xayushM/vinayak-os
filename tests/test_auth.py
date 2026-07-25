"""Unit tests for JWT issue/verify and the internal-key boundary."""
import types

import pytest
from fastapi import HTTPException

from vinayak.api.routes import auth


def test_jwt_roundtrip():
    tok = auth._issue_jwt("owner@vinayak.com", "kbrushes")
    payload = auth._verify_jwt(tok)
    assert payload.sub == "owner@vinayak.com"
    assert payload.company_id == "kbrushes"


def test_jwt_tampered_token_rejected():
    tok = auth._issue_jwt("owner@vinayak.com", "kbrushes")
    with pytest.raises(HTTPException) as exc:
        auth._verify_jwt(tok[:-2] + "xx")
    assert exc.value.status_code == 401


def _req(headers: dict):
    return types.SimpleNamespace(headers=headers)


def test_internal_key_rejects_wrong_key(monkeypatch):
    monkeypatch.setattr(auth, "INTERNAL_KEY", "right-key")
    with pytest.raises(HTTPException) as exc:
        auth.require_internal_key(_req({"X-Internal-Key": "wrong-key"}))
    assert exc.value.status_code == 403


def test_internal_key_rejects_missing_header(monkeypatch):
    monkeypatch.setattr(auth, "INTERNAL_KEY", "right-key")
    with pytest.raises(HTTPException):
        auth.require_internal_key(_req({}))


def test_internal_key_accepts_correct_key(monkeypatch):
    monkeypatch.setattr(auth, "INTERNAL_KEY", "right-key")
    auth.require_internal_key(_req({"X-Internal-Key": "right-key"}))  # no raise
