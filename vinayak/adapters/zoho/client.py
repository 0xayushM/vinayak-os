"""
adapters/zoho/client.py
────────────────────────
Paginated GET client for Zoho Books.

  fetch_all(creds, "invoices", "invoices")  →  every invoice header dict

Zoho conventions handled here:
  • organization_id required on every request
  • pagination: page/per_page (max 200) + page_context.has_more_page
  • rate limit: 100 req/min/org — we throttle to ~50 to leave headroom for
    other consumers of the same org
  • 429/5xx → exponential backoff; 401 → force token refresh once
"""
from __future__ import annotations

import logging
import time

import requests

from vinayak.adapters.zoho.auth import ZohoCreds, get_access_token, _cache_for

logger = logging.getLogger(__name__)

_MIN_INTERVAL = 60.0 / 50          # ~50 req/min
_last_call = 0.0
PER_PAGE = 200
MAX_PAGES = 500                    # safety cap (100k rows/resource)


def _throttle() -> None:
    global _last_call
    wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def _get(session: requests.Session, creds: ZohoCreds, resource: str,
         params: dict, max_retries: int = 4) -> dict:
    url = f"{creds.books_base}/{resource}"
    for attempt in range(max_retries):
        _throttle()
        token = get_access_token(creds)
        try:
            resp = session.get(url, params={**params, "organization_id": creds.organization_id},
                               headers={"Authorization": f"Zoho-oauthtoken {token}"},
                               timeout=60)
        except requests.RequestException as exc:
            logger.warning("zoho GET %s network error (attempt %d): %s", resource, attempt + 1, exc)
            time.sleep(2 ** attempt * 2)
            continue

        if resp.status_code == 401 and attempt == 0:
            # stale token — bust the cache and retry once immediately
            _cache_for(creds).expires_at = 0.0
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            logger.warning("zoho GET %s HTTP %d — backing off (attempt %d)",
                           resource, resp.status_code, attempt + 1)
            time.sleep(2 ** attempt * 5)
            continue
        if not resp.ok:
            raise RuntimeError(f"Zoho {resource} failed: HTTP {resp.status_code} — {resp.text[:300]}")
        body = resp.json()
        # Zoho wraps errors: code != 0 is an application-level error
        if body.get("code") not in (0, None):
            raise RuntimeError(f"Zoho {resource} error code {body.get('code')}: {body.get('message')}")
        return body

    raise RuntimeError(f"Zoho {resource}: failed after {max_retries} attempts")


def fetch_all(creds: ZohoCreds, resource: str, list_key: str,
              params: dict | None = None) -> list[dict]:
    """Walk every page of a list endpoint; returns the concatenated rows."""
    rows: list[dict] = []
    page = 1
    with requests.Session() as session:
        while page <= MAX_PAGES:
            body = _get(session, creds, resource,
                        {**(params or {}), "page": page, "per_page": PER_PAGE})
            rows.extend(body.get(list_key) or [])
            ctx = body.get("page_context") or {}
            if not ctx.get("has_more_page"):
                break
            page += 1
    logger.info("zoho fetch_all %s: %d rows over %d page(s)", resource, len(rows), page)
    return rows


def test_connection(creds: ZohoCreds) -> dict:
    """Cheap health check: fetch org info. Raises on any auth/config problem."""
    with requests.Session() as session:
        body = _get(session, creds, "organizations", {})
    orgs = body.get("organizations") or []
    match = [o for o in orgs if str(o.get("organization_id")) == str(creds.organization_id)]
    if not match:
        raise RuntimeError(
            f"Token works but organization_id {creds.organization_id} not among "
            f"accessible orgs: {[o.get('organization_id') for o in orgs]}")
    o = match[0]
    return {"organization_id": o.get("organization_id"), "name": o.get("name"),
            "currency": o.get("currency_code"), "plan": o.get("plan_name")}
