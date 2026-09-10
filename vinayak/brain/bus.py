"""
brain/bus.py
─────────────
The event bus: a Postgres table, on purpose.

Volume here is a few hundred events per company per day. Redis or a broker
would add infrastructure to fail without buying anything a table cannot do,
and a table gives two things a broker does not: events are in the same
transaction as the data that produced them, and last week's events are still
there to read when someone asks why the brain did something.

The one idea worth understanding is `dedupe_key`. Detectors are pure
functions of the current data and run every hour, so they re-derive the same
facts on every pass. The key is the identity of the FACT — "invoice INV-4471
crossed the 60-day rung" — so the unique index turns an hourly re-derivation
into a single event. That is what stops the same customer being chased once
an hour until they pay.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# Events older than this are never handed to a consumer. If the worker was
# down for two days, nobody wants Tuesday's chases going out on Thursday.
MAX_EVENT_AGE_HOURS = 36


def emit(conn, company_id: str, event_type: str, *, dedupe_key: str | None = None,
         entity_ref: str | None = None, payload: dict | None = None,
         severity: int = 0, source: str | None = None,
         run_id: int | None = None) -> int | None:
    """Record a fact. Returns the new event id, or None when the fact was
    already recorded (the common case on the second and later passes).

    Never commits: the caller owns the transaction, so a detector that fails
    halfway leaves no events behind.
    """
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO events
                 (company_id, event_type, dedupe_key, entity_ref, payload,
                  severity, source, run_id)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT DO NOTHING
               RETURNING id""",
            (company_id, event_type, dedupe_key, entity_ref,
             json.dumps(payload or {}, default=str), severity, source, run_id),
        )
        row = cur.fetchone()
    return int(row[0]) if row else None


def pending(conn, company_id: str, *, event_types: list[str] | None = None,
            limit: int = 100) -> list[dict]:
    """Unprocessed events, oldest first, never older than MAX_EVENT_AGE_HOURS.

    FOR UPDATE SKIP LOCKED so a second worker process can be started without
    two of them proposing the same action.
    """
    sql = """SELECT id, event_type, entity_ref, payload, severity, source, created_at
               FROM events
              WHERE company_id = %s
                AND processed_at IS NULL
                AND created_at > NOW() - (%s * INTERVAL '1 hour')"""
    params: list = [company_id, MAX_EVENT_AGE_HOURS]
    if event_types:
        sql += " AND event_type = ANY(%s)"
        params.append(event_types)
    sql += " ORDER BY created_at LIMIT %s FOR UPDATE SKIP LOCKED"
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [{"id": int(r[0]), "event_type": r[1], "entity_ref": r[2],
             "payload": r[3] or {}, "severity": int(r[4] or 0), "source": r[5],
             "created_at": r[6].isoformat() if r[6] else None} for r in rows]


def mark_processed(conn, event_id: int, *, by: str, outcome: dict | None = None) -> None:
    """Close an event. `outcome` says what the consumer did with it — the
    action id it proposed, or the reason it decided to do nothing — because
    an event that was deliberately ignored looks exactly like a bug otherwise.
    """
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE events
                  SET processed_at = NOW(), processed_by = %s, outcome = %s
                WHERE id = %s""",
            (by, json.dumps(outcome or {}, default=str), event_id),
        )


def expire_stale(conn, company_id: str) -> int:
    """Close events that aged out unprocessed, so they are not mistaken for a
    backlog. Returns how many were expired."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE events
                  SET processed_at = NOW(), processed_by = 'expired',
                      outcome = '{"reason": "older than the action window"}'::jsonb
                WHERE company_id = %s AND processed_at IS NULL
                  AND created_at <= NOW() - (%s * INTERVAL '1 hour')""",
            (company_id, MAX_EVENT_AGE_HOURS),
        )
        return cur.rowcount or 0


def recent(conn, company_id: str, limit: int = 50) -> list[dict]:
    """The event feed, for the Business Brain page."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, event_type, entity_ref, payload, severity, source,
                      created_at, processed_at, processed_by, outcome
                 FROM events
                WHERE company_id = %s
                ORDER BY created_at DESC LIMIT %s""",
            (company_id, limit),
        )
        rows = cur.fetchall()
    return [{"id": int(r[0]), "event_type": r[1], "entity_ref": r[2],
             "payload": r[3] or {}, "severity": int(r[4] or 0), "source": r[5],
             "created_at": r[6].isoformat() if r[6] else None,
             "processed_at": r[7].isoformat() if r[7] else None,
             "processed_by": r[8], "outcome": r[9] or {}} for r in rows]
