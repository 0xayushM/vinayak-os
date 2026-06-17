"""
memory/store.py
────────────────
Layer 2 — Context & Memory. The business profile (static, seeded at onboarding)
and the memory-fact store (durable, decaying knowledge captured from the owner).

The capture rule: when the owner confirms or corrects something, persist it as a
structured fact and reload it on every subsequent query about that entity — until
the fact goes stale. The decay handling is what keeps our own memory from becoming
the confident-wrong failure we are trying to prevent.

Public surface:
  get_profile / upsert_profile
  write_fact(...)              -> supersedes any prior active fact for the same key
  active_facts(...)           -> current facts for an entity (or whole company)
  supersede_fact / delete_fact
  load_context(company_id, entity_ref) -> {profile, facts}   (for Phase 3 reasoning)
  run_decay(company_id)       -> time-based + data-contradiction staleness sweep
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)


# ── Business profile ──────────────────────────────────────────────────────────
_PROFILE_COLS = [
    "industry", "sub_vertical", "fiscal_year_start", "gst_registered",
    "base_currency", "healthy_margin_pct", "seasonality", "key_customers",
    "kpis", "extras",
]


def get_profile(conn, company_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(_PROFILE_COLS)}, updated_at FROM business_profile WHERE company_id = %s",
            (company_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    out = dict(zip(_PROFILE_COLS, row[:-1]))
    out["updated_at"] = row[-1].isoformat() if row[-1] else None
    return out


def upsert_profile(conn, company_id: str, data: dict) -> dict:
    """Insert or update the company's business profile (partial updates allowed)."""
    fields = {k: data.get(k) for k in _PROFILE_COLS if k in data}
    if not fields:
        return get_profile(conn, company_id) or {}
    # JSONB columns must be serialised.
    for jcol in ("key_customers", "extras"):
        if jcol in fields and fields[jcol] is not None and not isinstance(fields[jcol], str):
            fields[jcol] = json.dumps(fields[jcol])
    cols = list(fields.keys())
    placeholders = ", ".join(["%s"] * len(cols))
    set_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
    with conn.cursor() as cur:
        cur.execute(
            f"""
            INSERT INTO business_profile (company_id, {', '.join(cols)}, updated_at)
            VALUES (%s, {placeholders}, now())
            ON CONFLICT (company_id) DO UPDATE SET {set_sql}, updated_at = now()
            """,
            [company_id] + [fields[c] for c in cols],
        )
    conn.commit()
    return get_profile(conn, company_id) or {}


# ── Memory facts ──────────────────────────────────────────────────────────────
def _fact_row(r) -> dict:
    keys = ["id", "entity_type", "entity_ref", "claim_key", "claim_value", "origin",
            "confidence", "created_at", "valid_until", "last_validated_at", "status",
            "superseded_by", "stale_reason"]
    d = dict(zip(keys, r))
    for t in ("created_at", "valid_until", "last_validated_at"):
        d[t] = d[t].isoformat() if d[t] else None
    d["id"] = str(d["id"])
    d["superseded_by"] = str(d["superseded_by"]) if d["superseded_by"] else None
    return d


_SELECT = """
    SELECT id, entity_type, entity_ref, claim_key, claim_value, origin, confidence,
           created_at, valid_until, last_validated_at, status, superseded_by, stale_reason
    FROM memory_fact
"""


def write_fact(
    conn, company_id: str, *, entity_type: str, entity_ref: str, claim_key: str,
    claim_value: Any, origin: str = "user_confirmed", confidence: float = 1.0,
    valid_until: str | None = None, source_msg_id: str | None = None,
) -> dict:
    """
    Persist a new fact. Any prior ACTIVE fact for the same (entity_ref, claim_key)
    is superseded — so 'the current value' is always a single active row.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO memory_fact
                (company_id, entity_type, entity_ref, claim_key, claim_value, origin,
                 confidence, valid_until, source_msg_id, last_validated_at, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, now(), 'active')
            RETURNING id
            """,
            (company_id, entity_type, entity_ref, claim_key, json.dumps(claim_value),
             origin, confidence, valid_until, source_msg_id),
        )
        new_id = cur.fetchone()[0]
        # Supersede the previous active fact(s) for this key.
        cur.execute(
            """
            UPDATE memory_fact
            SET status = 'superseded', superseded_by = %s
            WHERE company_id = %s AND entity_ref = %s AND claim_key = %s
              AND status = 'active' AND id <> %s
            """,
            (new_id, company_id, entity_ref, claim_key, new_id),
        )
        cur.execute(_SELECT + " WHERE id = %s", (new_id,))
        row = cur.fetchone()
    conn.commit()
    return _fact_row(row)


def active_facts(conn, company_id: str, entity_ref: str | None = None,
                 include_stale: bool = True) -> list[dict]:
    statuses = ("active", "stale") if include_stale else ("active",)
    params: list[Any] = [company_id, list(statuses)]
    where = "WHERE company_id = %s AND status = ANY(%s)"
    if entity_ref:
        where += " AND entity_ref = %s"
        params.append(entity_ref)
    with conn.cursor() as cur:
        cur.execute(_SELECT + where + " ORDER BY entity_ref, claim_key, created_at DESC", params)
        return [_fact_row(r) for r in cur.fetchall()]


def supersede_fact(conn, company_id: str, fact_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE memory_fact SET status = 'superseded' WHERE company_id = %s AND id = %s",
            (company_id, fact_id),
        )
    conn.commit()


# ── Context loader (used by Phase 3 reasoning) ────────────────────────────────
def load_context(conn, company_id: str, entity_ref: str | None = None) -> dict:
    """Everything the AI should know before answering: profile + active facts.
    Stale facts are included but flagged so the reasoner re-asks instead of trusting."""
    return {
        "profile": get_profile(conn, company_id),
        "facts": active_facts(conn, company_id, entity_ref, include_stale=True),
    }


# ── Decay — the part that keeps memory honest ─────────────────────────────────
def run_decay(conn, company_id: str) -> dict:
    """
    Mark facts stale by two signals:
      • time-based: valid_until in the past.
      • data-contradiction: a stated payment_terms_days that the customer's open
        invoices clearly violate (open invoices aging well past the stated terms).
    Stale facts are NOT deleted — they are flagged so the AI re-asks rather than
    silently repeating a now-wrong belief.
    """
    time_stale = 0
    contradiction_stale = 0
    with conn.cursor() as cur:
        # 1. Time-based expiry.
        cur.execute(
            """
            UPDATE memory_fact
            SET status = 'stale', stale_reason = 'expired'
            WHERE company_id = %s AND status = 'active'
              AND valid_until IS NOT NULL AND valid_until < now()
            """,
            (company_id,),
        )
        time_stale = cur.rowcount

        # 2. Data-contradiction for payment_terms_days.
        cur.execute(
            """
            SELECT id, entity_ref, claim_value
            FROM memory_fact
            WHERE company_id = %s AND status = 'active' AND claim_key = 'payment_terms_days'
            """,
            (company_id,),
        )
        for fact_id, entity_ref, claim_value in cur.fetchall():
            try:
                terms = int(claim_value)
            except (TypeError, ValueError):
                continue
            # entity_ref like 'customer:<name-or-code>' — match against AR by name/code.
            ref = entity_ref.split(":", 1)[-1] if entity_ref else ""
            cur.execute(
                """
                SELECT COALESCE(AVG(CURRENT_DATE - invoice_date), 0)
                FROM canon_ar_flat
                WHERE company_id = %s
                  AND COALESCE(outstanding_amount, 0) > 0
                  AND (LOWER(customer_name) = LOWER(%s) OR LOWER(COALESCE(customer_code,'')) = LOWER(%s))
                """,
                (company_id, ref, ref),
            )
            avg_age = float(cur.fetchone()[0] or 0)
            # Flag if open invoices are aging well past the stated terms.
            if terms > 0 and avg_age > terms * 1.5 and avg_age - terms >= 15:
                cur.execute(
                    """
                    UPDATE memory_fact SET status = 'stale',
                        stale_reason = %s
                    WHERE id = %s AND status = 'active'
                    """,
                    (f"open invoices aging ~{avg_age:.0f}d vs stated {terms}d terms", fact_id),
                )
                contradiction_stale += cur.rowcount
    conn.commit()
    return {"time_stale": time_stale, "contradiction_stale": contradiction_stale}
