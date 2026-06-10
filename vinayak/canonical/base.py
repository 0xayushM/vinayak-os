"""
canonical/base.py
──────────────────
The SourceAdapter contract (Layer 0). Every source — Tranzact today, Tally/Busy
later — implements this same interface, mapping its own chaos into the canonical
schema and logging anything it cannot confidently map to `ingest_issues`.

Contract:
    extract(conn, company_id)        -> raw rows from the source
    map(raw)                          -> CanonResult: a canonical dict OR Unmapped
    load(conn, company_id, rows)      -> upsert canonical rows (idempotent)

Two rules that matter (from the product doc):
  • Always keep `raw` — re-map later without re-fetching.
  • Log, don't guess — unmappable data goes to ingest_issues, never a plausible
    fake value, never a silent drop.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class Unmapped:
    """Returned by map() when a row cannot be confidently mapped."""
    object_type: str
    field: str
    reason: str
    raw_value: Any = None
    source_ref: str | None = None


@dataclass
class CanonRow:
    """A single mapped canonical row, tagged with its target table + key."""
    table: str                    # 'canon_sales_invoice' | ...
    object_type: str              # 'sales_invoice' | ...
    source_ref: str               # idempotent key within (company_id, source)
    fields: dict[str, Any]        # column → value (excludes envelope)
    confidence: float = 1.0
    raw: dict[str, Any] | None = None


CanonResult = CanonRow | Unmapped


@dataclass
class LoadStats:
    upserted: dict[str, int] = field(default_factory=dict)
    issues: int = 0


def log_issue(cur, company_id: str, source: str, issue: Unmapped) -> None:
    """Record an unmappable value in ingest_issues (the parser backlog)."""
    cur.execute(
        """
        INSERT INTO ingest_issues
            (company_id, source, source_ref, object_type, field, reason, raw_value)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (company_id, source, issue.source_ref, issue.object_type,
         issue.field, issue.reason, None if issue.raw_value is None else str(issue.raw_value)[:500]),
    )


class SourceAdapter(Protocol):
    source_name: str
    def rebuild(self, conn, company_id: str) -> LoadStats: ...
