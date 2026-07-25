"""
adapters/zoho/auth.py
──────────────────────
Zoho OAuth2, server-to-server ("Self Client" pattern):

  One-time, manual (per customer org, documented in docs/ZOHO_INTEGRATION.md):
    api-console.zoho.in → Self Client → generate grant code with scope
    ZohoBooks.fullaccess.READ → exchange for a REFRESH TOKEN.

  Runtime (this module):
    refresh_token → POST {accounts}/oauth/v2/token → access token (~1 hour).
    Tokens are cached per (dc, client_id, refresh_token) and renewed ~2 min
    before expiry. The refresh token itself does not expire unless revoked.

Zoho runs regional data centers; both the accounts host and the API host must
match the org's DC. Indian customers → 'in'.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

import requests

logger = logging.getLogger(__name__)

# dc → (accounts host, api host)
DCS = {
    "in":  ("https://accounts.zoho.in",     "https://www.zohoapis.in"),
    "com": ("https://accounts.zoho.com",    "https://www.zohoapis.com"),
    "eu":  ("https://accounts.zoho.eu",     "https://www.zohoapis.eu"),
    "au":  ("https://accounts.zoho.com.au", "https://www.zohoapis.com.au"),
}

_EARLY_REFRESH_SECS = 120


@dataclass
class ZohoCreds:
    client_id: str
    client_secret: str
    refresh_token: str
    organization_id: str
    dc: str = "in"

    @property
    def accounts_base(self) -> str:
        return DCS[self.dc][0]

    @property
    def books_base(self) -> str:
        return DCS[self.dc][1] + "/books/v3"


@dataclass
class _TokenCache:
    access_token: str = ""
    expires_at: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock)


_caches: dict[tuple, _TokenCache] = {}
_caches_lock = threading.Lock()


def _cache_for(creds: ZohoCreds) -> _TokenCache:
    key = (creds.dc, creds.client_id, creds.refresh_token)
    with _caches_lock:
        if key not in _caches:
            _caches[key] = _TokenCache()
        return _caches[key]


def get_access_token(creds: ZohoCreds) -> str:
    """Return a valid access token, refreshing if absent/near expiry."""
    cache = _cache_for(creds)
    with cache.lock:
        if cache.access_token and time.time() < cache.expires_at - _EARLY_REFRESH_SECS:
            return cache.access_token

        url = f"{creds.accounts_base}/oauth/v2/token"
        resp = requests.post(url, data={
            "grant_type": "refresh_token",
            "client_id": creds.client_id,
            "client_secret": creds.client_secret,
            "refresh_token": creds.refresh_token,
        }, timeout=30)
        try:
            body = resp.json()
        except ValueError:
            raise RuntimeError(
                f"Zoho token endpoint returned non-JSON (HTTP {resp.status_code})")
        if "access_token" not in body:
            # Zoho reports errors in-band, e.g. {"error": "invalid_code"}
            raise RuntimeError(f"Zoho token refresh failed: {body}")

        cache.access_token = body["access_token"]
        cache.expires_at = time.time() + float(body.get("expires_in", 3600))
        logger.info("Zoho: refreshed access token (dc=%s, org=%s)",
                    creds.dc, creds.organization_id)
        return cache.access_token
