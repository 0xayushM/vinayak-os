"""
pipelines/helpers.py
─────────────────────
Shared utilities for all TranzAct pipeline RowSchemas.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from typing import Any, Optional


def stable_row_id(*parts: Any) -> str:
    """
    Deterministic content hash used as the upsert key (raw_id) for a row.

    TranzAct returns a fresh `uuid` on every fetch, so keying the upsert on it
    let each sync re-insert an identical business row under a new id — producing
    7×–32× duplicates. Hashing the *business-identifying* fields instead makes
    re-syncing the same record a no-op (ON CONFLICT updates the existing row),
    which is what stops the duplication at the source.

    Pass the natural-key fields (dates as ISO strings, numbers as-is). Order
    matters and must stay stable for a given pipeline.
    """
    payload = json.dumps([_norm(p) for p in parts], separators=(",", ":"), default=str)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def num(v: Any) -> Optional[float]:
    """Coerce a value to float (or None) so numeric key parts hash identically
    whether they arrive as int, float, numeric string, or DB Decimal."""
    if v is None or v == "":
        return None
    try:
        return round(float(v), 4)
    except (ValueError, TypeError):
        return None


def _norm(v: Any) -> Any:
    """Normalise a key part so equal values hash identically across syncs."""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    if isinstance(v, float):
        # Avoid 22177.11 vs 22177.110000001 mismatches.
        return round(v, 4)
    return str(v).strip()


def epoch_to_date(v: Any) -> Optional[date]:
    """
    Coerce a value to a Python date.

    Handles:
      - None / empty string → None
      - date instance        → pass through
      - int/float > 1e12     → epoch milliseconds (TranzAct default)
      - int/float > 1e9      → epoch seconds
      - "DD/MM/YYYY" string  → parse with day-first
      - "YYYY-MM-DD" string  → ISO parse (first 10 chars)
    """
    if v is None or v == "":
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, (int, float)):
        if v > 1_000_000_000_000:
            return datetime.fromtimestamp(v / 1000.0, tz=timezone.utc).date()
        if v > 1_000_000_000:
            return datetime.fromtimestamp(float(v), tz=timezone.utc).date()
    try:
        s = str(v).strip()
        if len(s) == 10 and s[2] == "/" and s[5] == "/":
            d, m, y = s.split("/")
            return date(int(y), int(m), int(d))
        return date.fromisoformat(s[:10])
    except (ValueError, TypeError):
        return None
