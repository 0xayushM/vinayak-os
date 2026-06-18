"""
adapters/tranzact/client.py
────────────────────────────
Single public function: fetch_report()

Handles:
  • Attaches Bearer token via auth.get_access_token()
  • Pagination loop — fetches all pages until exhausted
  • Exponential backoff on 429 / 5xx responses
  • 401 → force token refresh → one retry before raising
  • Rate limiting: enforces TRANZACT_REQUESTS_PER_MINUTE (default 8/min)

Confirmed endpoint (2026-05-22):
  POST https://reporting.letstranzact.com/generate_report
  Response: {"success": true, "data": {"results": [...], "total_items": N, ...}}
  Login:    POST https://be.letstranzact.com/main/login/password-login/
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

from vinayak.adapters.tranzact.auth import get_access_token
from vinayak.config import (
    TRANZACT_BASE_URL,
    TRANZACT_REPORTING_URL,
    TRANZACT_REQUESTS_PER_MINUTE,
)

logger = logging.getLogger(__name__)


# ── Per-account credentials ──────────────────────────────────────────────────
# In multi-brand mode each TranzAct account has its own login. Credentials are
# threaded explicitly from the pipeline layer down to the token fetch so that a
# sync for brand A never authenticates as brand B. When no creds are supplied
# (e.g. legacy single-account callers) we fall back to the env-var account.

@dataclass(frozen=True)
class TranzactCreds:
    email: str
    password: str
    base_url: str = TRANZACT_BASE_URL


# ── Rate limiter (module-level state) ────────────────────────────────────────

_MIN_INTERVAL: float = 60.0 / TRANZACT_REQUESTS_PER_MINUTE  # seconds between calls
_last_request_at: float = 0.0

# Hard cap on pages per report fetch. TranzAct serves ~50 rows/page and ignores
# per_page, so a year of invoices is a few hundred pages at most; this only
# guards against an unbounded loop if the server stops sending total_items.
_MAX_PAGES: int = 2000


def _throttle() -> None:
    """Block until at least _MIN_INTERVAL seconds have passed since last request."""
    global _last_request_at
    elapsed = time.monotonic() - _last_request_at
    wait = _MIN_INTERVAL - elapsed
    if wait > 0:
        time.sleep(wait)
    _last_request_at = time.monotonic()


# ── Response shape helpers (confirmed 2026-05-22) ────────────────────────────
# Response: {"success": true, "data": {"results": [...], "total_items": N, ...}}

def _get_rows(body: dict) -> list[dict]:
    """Extract the list of data rows from a /generate_report response."""
    data = body.get("data", {})
    if isinstance(data, dict):
        results = data.get("results")
        if isinstance(results, list):
            return results
    # Legacy fallbacks
    if isinstance(data, list):
        return data
    return []


def _get_total_items(body: dict) -> int:
    """Total row count the server reports for this report, or 0 if unknown.

    NOTE: do NOT derive a page count from this divided by the per_page we
    *requested*. TranzAct ignores per_page and serves a fixed page size (≈50),
    so ceil(total_items / requested_per_page) under-counts the pages and the
    fetch stops early, silently dropping the older rows. Pagination instead
    loops until it has collected `total_items` rows (or a page comes back empty).
    """
    data = body.get("data", {})
    if isinstance(data, dict):
        try:
            return int(data.get("total_items", 0))
        except (TypeError, ValueError):
            return 0
    return 0


# ── Core request function ─────────────────────────────────────────────────────

def _post_with_retry(
    session: requests.Session,
    payload: dict,
    creds: TranzactCreds,
    max_retries: int = 3,
) -> dict:
    """
    POST to /generate_report with Bearer token, backoff on errors.
    Returns the parsed JSON body.
    Raises RuntimeError after exhausting retries.
    """
    prev_5xx_signature: tuple[int, str] | None = None

    for attempt in range(max_retries):
        _throttle()
        token = get_access_token(
            base_url=creds.base_url,
            email=creds.email,
            password=creds.password,
        )
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        try:
            resp = session.post(
                f"{TRANZACT_REPORTING_URL}/generate_report",
                headers=headers,
                json=payload,
                timeout=90,
            )
        except requests.RequestException as exc:
            logger.warning("fetch_report: network error (attempt %d): %s", attempt + 1, exc)
            time.sleep(2 ** attempt * 3)
            continue

        if resp.status_code == 401:
            logger.warning("fetch_report: 401 — forcing token refresh (attempt %d)", attempt + 1)
            token = get_access_token(
                base_url=creds.base_url,
                email=creds.email,
                password=creds.password,
                force_refresh=True,
            )
            continue  # retry immediately after forced refresh

        # 429 is always worth retrying (transient rate limit).
        if resp.status_code == 429:
            wait = 2 ** attempt * 5  # 5 s, 10 s, 20 s
            logger.warning(
                "fetch_report: HTTP 429 — backing off %ds (attempt %d)",
                wait, attempt + 1,
            )
            time.sleep(wait)
            continue

        # 5xx: retry transient errors, but fast-fail on a *deterministic* one.
        # A server error that returns the byte-for-byte same body on a fresh
        # attempt is not going to fix itself by waiting — it's a bad request the
        # server mis-handles (e.g. a missing/mismatched report param). Bail
        # immediately instead of burning ~35s on identical retries.
        if resp.status_code >= 500:
            signature = (resp.status_code, resp.text[:500])
            if prev_5xx_signature == signature:
                logger.error(
                    "fetch_report: HTTP %d repeated identical response — "
                    "treating as deterministic failure, not retrying. body=%s",
                    resp.status_code, resp.text[:500],
                )
                raise RuntimeError(
                    f"fetch_report: deterministic HTTP {resp.status_code} from "
                    f"/generate_report for payload {payload} — body={resp.text[:500]}"
                )
            prev_5xx_signature = signature
            wait = 2 ** attempt * 5  # 5 s, 10 s, 20 s
            logger.warning(
                "fetch_report: HTTP %d — backing off %ds (attempt %d)",
                resp.status_code, wait, attempt + 1,
            )
            time.sleep(wait)
            continue

        resp.raise_for_status()
        return resp.json()

    # All retries exhausted — log the last upstream context for diagnosis.
    detail = ""
    try:
        detail = f" last_status={resp.status_code} body={resp.text[:300]}"  # type: ignore[name-defined]
    except Exception:  # noqa: BLE001
        pass
    page = payload.get("pagination", {}).get("page")
    logger.error(
        "fetch_report: report_id=%s page=%s — failed after %d attempts.%s",
        payload.get("report", {}).get("id"), page, max_retries, detail,
    )
    raise RuntimeError(
        f"Report fetch failed after {max_retries} attempts (page {page})."
    )


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_report(
    report_id: str,
    filters: dict | None = None,
    per_page: int = 200,
    max_seconds: float | None = None,
    stats: dict | None = None,
    creds: TranzactCreds = ...,  # type: ignore[assignment]
    start_page: int = 1,
    max_pages: int | None = None,
) -> list[dict]:
    """
    Fetch rows of a TranzAct report by walking pages.

    By default (start_page=1, max_pages=None) it pulls the ENTIRE report. Pass
    start_page / max_pages to fetch one resumable CHUNK — the basis of the
    cursor-driven migration (see docs/RESUMABLE_SYNC.md).

    Args:
        report_id:  String report ID (e.g. "29" for Sales Invoice Register)
        filters:    Dict merged into the request payload (unused for report 29 —
                    TranzAct has no server-side date filter).
        per_page:   Page size we request. NOTE: TranzAct ignores this and serves
                    a fixed page (~50 rows); `page` is therefore a 50-row index.
        max_seconds: Wall-clock cap; paging stops once elapsed (partial result).
        stats:      Optional dict populated with fetch metadata:
                      truncated      — stopped early due to the time cap
                      pages_fetched  — pages fetched THIS call
                      last_page      — the last page number fetched
                      total_items    — server-reported total row count
                      reached_end    — a page returned no more data (fully done)
                      more_available — there are likely more pages to fetch
        creds:      Per-brand TranzAct credentials (required).
        start_page: First page to request (>=1). Use for resume.
        max_pages:  Max pages to fetch this call (chunk size). None = until done.

    Returns:
        Flat list of row dicts for the pages fetched this call.
    """
    if creds is ...:
        raise ValueError(
            "fetch_report: creds is required. TranzAct credentials must be "
            "stored per brand via POST /connections/tranzact and passed through "
            "the pipeline run — they are no longer read from environment variables."
        )
    all_rows: list[dict] = []
    page = max(1, start_page)
    pages_this_call = 0
    truncated = False
    reached_end = False
    total_items = 0
    last_page = page - 1
    last_page_rows = 0
    deadline = (time.monotonic() + max_seconds) if max_seconds else None

    with requests.Session() as session:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                truncated = True
                logger.warning(
                    "fetch_report: report_id=%s hit %.0fs time cap at page %d — "
                    "returning %d rows this call (partial)",
                    report_id, max_seconds, page, len(all_rows),
                )
                break
            if max_pages is not None and pages_this_call >= max_pages:
                break

            payload: dict[str, Any] = {
                "report": {"id": report_id},
                "pagination": {"page": page, "per_page": per_page},
            }
            if filters:
                payload.update(filters)

            try:
                body = _post_with_retry(session, payload, creds)
            except Exception:
                # A page failed after retries. If we already collected rows this
                # call AND the server never reported a total (typical of snapshot
                # reports that error on an out-of-range page), treat it as the end
                # of data rather than failing the whole report. Otherwise re-raise
                # so a genuine failure is surfaced (and logged in _post_with_retry).
                if all_rows and not total_items:
                    logger.warning(
                        "fetch_report: report_id=%s page=%d failed after retries; "
                        "%d rows already collected and no total reported — treating "
                        "as end of data.", report_id, page, len(all_rows),
                    )
                    reached_end = True
                    break
                raise

            rows = _get_rows(body)
            all_rows.extend(rows)
            total_items = _get_total_items(body)
            pages_this_call += 1
            last_page = page
            last_page_rows = len(rows)

            logger.debug(
                "fetch_report: report_id=%s page=%d → %d rows (total_items=%s)",
                report_id, page, len(rows), total_items or "?",
            )

            # Page size is whatever the server decides (it ignores per_page), so
            # we never derive a page count from total_items / per_page.
            if not rows:
                reached_end = True
                break
            # Only valid as an end-signal for a full walk from page 1.
            if start_page == 1 and total_items and len(all_rows) >= total_items:
                reached_end = True
                break
            if page >= _MAX_PAGES:
                logger.warning(
                    "fetch_report: report_id=%s hit safety cap of %d pages — stopping",
                    report_id, _MAX_PAGES,
                )
                break
            page += 1

    more_available = (not reached_end) and last_page_rows > 0

    if stats is not None:
        stats["truncated"] = truncated
        stats["pages_fetched"] = pages_this_call
        stats["last_page"] = last_page
        stats["total_items"] = total_items
        stats["reached_end"] = reached_end
        stats["more_available"] = more_available

    logger.info(
        "fetch_report: report_id=%s pages=%d rows=%d last_page=%d more=%s",
        report_id, pages_this_call, len(all_rows), last_page, more_available,
    )
    return all_rows
