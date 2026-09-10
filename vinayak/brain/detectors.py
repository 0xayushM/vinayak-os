"""
brain/detectors.py
───────────────────
Three watchers that read the data and emit typed events. Between them they
cover the three things worth waking up for: money that has slipped a rung,
a feed that has gone quiet, and something in the numbers that does not look
like the rest of the numbers.

Every detector here is a query and a threshold. No model reads this data and
no model decides what is worth an event — the reference document's rule is
that the model proposes and deterministic code disposes, and detection is
firmly on the deterministic side. What the model may later do is write the
sentence that goes to a customer, and even that is a proposal.

Each returns the number of NEW events emitted. Re-running a detector minutes
later emits nothing, because the dedupe key is the identity of the fact.
"""
from __future__ import annotations

import logging
from datetime import date

from vinayak.brain import bus

logger = logging.getLogger(__name__)

# The rungs of the collections ladder, in days past due. An invoice emits one
# event per rung it crosses, ever — so a customer moves up the ladder rather
# than being chased with the same message every week.
RUNGS = (7, 30, 60, 90)

# Below this, chasing costs more than it recovers.
MIN_CHASE_AMOUNT = 5_000.0

# How many invoices one pass may raise. A first sync of a neglected book
# would otherwise fill the Inbox with two hundred proposals on day one; the
# cap turns that into a fortnight of manageable mornings, worst first.
MAX_RUNG_EVENTS_PER_PASS = 15

# A feed this far behind is a fact worth an event, not just a grey badge.
STALE_HOURS = 25


def _rung_for(days_overdue: int) -> int | None:
    """The highest rung this invoice has passed, or None if it is not late
    enough to matter."""
    passed = [r for r in RUNGS if days_overdue >= r]
    return max(passed) if passed else None


def detect_overdue_rung(conn, company_id: str, *, run_id: int | None = None,
                        config: dict | None = None) -> int:
    """Invoices that have crossed a collections rung.

    The event is per (invoice, rung), so an invoice that is 95 days late and
    was never chased emits one event at rung 90 — not four. The consumer
    turns it into a draft chase at that rung's tone.
    """
    cfg = config or {}
    min_amount = float(cfg.get("min_amount", MIN_CHASE_AMOUNT))
    cap = int(cfg.get("max_per_pass", MAX_RUNG_EVENTS_PER_PASS))

    with conn.cursor() as cur:
        cur.execute("""
            SELECT customer_name, invoice_number, due_date,
                   COALESCE(outstanding_amount, 0) AS outstanding,
                   (CURRENT_DATE - due_date) AS days_overdue
              FROM canon_ar_flat
             WHERE company_id = %s
               AND COALESCE(outstanding_amount, 0) >= %s
               AND due_date IS NOT NULL
               AND due_date < CURRENT_DATE
             ORDER BY (CURRENT_DATE - due_date) * COALESCE(outstanding_amount, 0) DESC
             LIMIT 400
        """, (company_id, min_amount))
        rows = cur.fetchall()

    emitted = 0
    for customer, number, due, outstanding, days in rows:
        if emitted >= cap:
            break
        rung = _rung_for(int(days or 0))
        if rung is None:
            continue
        new_id = bus.emit(
            conn, company_id, "invoice.overdue_rung",
            dedupe_key=f"{number}:rung{rung}",
            entity_ref=f"customer:{customer}",
            severity=min(90, 30 + rung // 2),
            source="detect.overdue_rung",
            run_id=run_id,
            payload={"customer_name": customer, "invoice_number": number,
                     "due_date": due.isoformat() if isinstance(due, date) else due,
                     "outstanding": float(outstanding or 0),
                     "days_overdue": int(days or 0), "rung": rung},
        )
        if new_id:
            emitted += 1
    return emitted


def detect_data_stale(conn, company_id: str, *, run_id: int | None = None,
                      config: dict | None = None) -> int:
    """A feed that has stopped arriving.

    This one matters more than it looks. Every other number in the product is
    only as true as its last sync, so a silent pipeline does not make the
    dashboard wrong-looking — it makes it confidently wrong. The dedupe key
    carries the calendar day, so a feed that stays broken says so once a day
    rather than once an hour.
    """
    cfg = config or {}
    hours = int(cfg.get("stale_hours", STALE_HOURS))
    today = date.today().isoformat()

    with conn.cursor() as cur:
        cur.execute("""
            SELECT pipeline_name,
                   MAX(completed_at) AS last_ok,
                   EXTRACT(EPOCH FROM (NOW() - MAX(completed_at))) / 3600 AS hours_ago
              FROM tz_sync_runs
             WHERE company_id = %s AND status = 'success'
             GROUP BY pipeline_name
            HAVING MAX(completed_at) < NOW() - (%s * INTERVAL '1 hour')
             ORDER BY 3 DESC
        """, (company_id, hours))
        rows = cur.fetchall()

    emitted = 0
    for pipeline_name, last_ok, hours_ago in rows:
        new_id = bus.emit(
            conn, company_id, "data.stale",
            dedupe_key=f"{pipeline_name}:{today}",
            entity_ref=f"pipeline:{pipeline_name}",
            severity=70,
            source="detect.data_stale",
            run_id=run_id,
            payload={"pipeline": pipeline_name,
                     "last_success": last_ok.isoformat() if last_ok else None,
                     "hours_ago": round(float(hours_ago or 0), 1)},
        )
        if new_id:
            emitted += 1
    return emitted


def detect_anomaly(conn, company_id: str, *, run_id: int | None = None,
                   config: dict | None = None) -> int:
    """Negative stock, an outsized invoice, a vendor price jump.

    The rules already exist — Pulse computes them for the anomalies card. The
    detector's job is only to give them a life outside the moment somebody
    happens to open the page: an anomaly nobody was looking at still becomes
    an event, and therefore still reaches the Inbox or the brief.

    'data_stale' is filtered out here because it has its own detector with a
    proper per-day key; letting both emit would double-count the same fact.
    """
    from vinayak.schema.pulse import get_anomalies

    cfg = config or {}
    min_severity = int(cfg.get("min_severity", 40))
    today = date.today().isoformat()

    found = get_anomalies(conn, company_id, cap=12)
    emitted = 0
    for item in found.get("items", []):
        if item.get("kind") == "data_stale":
            continue
        if int(item.get("severity", 0)) < min_severity:
            continue
        entity = item.get("entity_ref") or item.get("kind")
        new_id = bus.emit(
            conn, company_id, "anomaly.detected",
            # Same anomaly, same day, one event. An outsized invoice that is
            # still outsized tomorrow is not news twice.
            dedupe_key=f"{item['kind']}:{entity}:{today}",
            entity_ref=item.get("entity_ref"),
            severity=int(item.get("severity", 0)),
            source="detect.anomaly",
            run_id=run_id,
            payload=item,
        )
        if new_id:
            emitted += 1
    return emitted


DETECTORS = {
    "detect.overdue_rung": detect_overdue_rung,
    "detect.data_stale": detect_data_stale,
    "detect.anomaly": detect_anomaly,
}
