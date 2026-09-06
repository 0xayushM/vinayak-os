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


# ── Supabase mode (SUPABASE_JWT_SECRET set) ───────────────────────────────────
def _req2(headers=None, cookies=None):
    return types.SimpleNamespace(headers=headers or {}, cookies=cookies or {})


def _supabase_token(secret, email, sub="uuid-1", exp=None):
    import time
    return jwt.encode(
        {"sub": sub, "email": email, "aud": "authenticated", "exp": exp or (time.time() + 3600)},
        secret, algorithm="HS256",
    )


from jose import jwt  # noqa: E402  (used by the helper above)


def test_supabase_token_verified_and_company_resolved(monkeypatch):
    monkeypatch.setattr(auth, "SUPABASE_MODE", True)
    monkeypatch.setattr(auth, "SUPABASE_JWT_SECRET", "test-secret")
    monkeypatch.setattr(auth, "_resolve_company", lambda email: "kbrushes")
    tok = _supabase_token("test-secret", "owner@vinayak.com")
    payload = auth.get_current_user(_req2(headers={"Authorization": f"Bearer {tok}"}))
    assert payload.sub == "owner@vinayak.com"
    assert payload.company_id == "kbrushes"
    assert payload.user_id == "uuid-1"


def test_supabase_rejects_wrong_secret(monkeypatch):
    monkeypatch.setattr(auth, "SUPABASE_MODE", True)
    monkeypatch.setattr(auth, "SUPABASE_JWT_SECRET", "test-secret")
    tok = _supabase_token("WRONG-secret", "owner@vinayak.com")
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_req2(headers={"Authorization": f"Bearer {tok}"}))
    assert exc.value.status_code == 401


def test_supabase_missing_token_is_401(monkeypatch):
    monkeypatch.setattr(auth, "SUPABASE_MODE", True)
    monkeypatch.setattr(auth, "SUPABASE_JWT_SECRET", "test-secret")
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(_req2())
    assert exc.value.status_code == 401


class _FakeCur:
    def __init__(self, row): self._row = row
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def execute(self, *a): pass
    def fetchone(self): return self._row

class _FakeConn:
    def __init__(self, row): self._row = row
    def cursor(self): return _FakeCur(self._row)
    def close(self): pass


def test_resolve_company_fails_closed_for_unknown_email(monkeypatch):
    """A valid Supabase account NOT in the users allowlist must be denied (403),
    never silently treated as a global admin."""
    import vinayak.db.session as S
    monkeypatch.setattr(S.db, "connect", lambda: _FakeConn(None))
    with pytest.raises(HTTPException) as exc:
        auth._resolve_company("stranger@example.com")
    assert exc.value.status_code == 403


def test_resolve_company_null_company_is_global_admin(monkeypatch):
    import vinayak.db.session as S
    monkeypatch.setattr(S.db, "connect", lambda: _FakeConn((None,)))   # row exists, company NULL
    assert auth._resolve_company("owner@vinayak.com") == ""            # '' = global admin


def test_resolve_company_returns_mapped_company(monkeypatch):
    import vinayak.db.session as S
    monkeypatch.setattr(S.db, "connect", lambda: _FakeConn(("kbrushes",)))
    assert auth._resolve_company("owner@vinayak.com") == "kbrushes"


def test_legacy_cookie_path_unaffected(monkeypatch):
    monkeypatch.setattr(auth, "SUPABASE_MODE", False)
    tok = auth._issue_jwt("owner@vinayak.com", "kbrushes")
    payload = auth.get_current_user(_req2(cookies={auth.COOKIE_NAME: tok}))
    assert payload.company_id == "kbrushes"
