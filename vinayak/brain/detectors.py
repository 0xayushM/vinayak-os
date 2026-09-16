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

# The ladder itself lives in vinayak/collections.py — one definition, or the
# two drift and the detector starts disagreeing with the letter it triggers.
# Below this, chasing costs more than it recovers.
MIN_CHASE_AMOUNT = 5_000.0

# How many invoices one pass may raise. A first sync of a neglected book
# would otherwise fill the Inbox with two hundred proposals on day one; the
# cap turns that into a fortnight of manageable mornings, worst first.
MAX_RUNG_EVENTS_PER_PASS = 15

# A feed this far behind is a fact worth an event, not just a grey badge.
STALE_HOURS = 25


def detect_overdue_rung(conn, company_id: str, *, run_id: int | None = None,
                        config: dict | None = None) -> int:
    """Customers who have earned the next rung of the collections ladder.

    Per CUSTOMER, not per invoice. Chasing is a conversation with a person
    about their account, and a customer with nine late invoices should get one
    call, not nine emails — which is what the per-invoice version produced.

    Everything that decides whether a chase is allowed lives in
    `collections.decide`: the ladder, the cooldown between rungs, an open
    promise to pay, a manual pause, and the dispute flag. The detector's job
    is to ask, not to judge.
    """
    from vinayak import collections as C

    cfg = config or {}
    min_amount = float(cfg.get("min_amount", MIN_CHASE_AMOUNT))
    cap = int(cfg.get("max_per_pass", MAX_RUNG_EVENTS_PER_PASS))

    # A customer who has cleared starts again at the bottom, so the next
    # reminder they ever get is a first reminder.
    C.reset_if_settled(conn, company_id)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT customer_name,
                   COALESCE(SUM(outstanding_amount), 0)  AS outstanding,
                   MAX(CURRENT_DATE - due_date)          AS days_overdue,
                   COUNT(*)                              AS invoices
              FROM canon_ar_flat
             WHERE company_id = %s
               AND COALESCE(outstanding_amount, 0) > 0
               AND due_date IS NOT NULL
               AND due_date < CURRENT_DATE
             GROUP BY customer_name
            HAVING COALESCE(SUM(outstanding_amount), 0) >= %s
             ORDER BY MAX(CURRENT_DATE - due_date) * COALESCE(SUM(outstanding_amount), 0) DESC
             LIMIT 400
        """, (company_id, min_amount))
        rows = cur.fetchall()

    states = C.all_states(conn, company_id)
    promises = C.open_promises(conn, company_id)

    emitted = 0
    for customer, outstanding, days, invoices in rows:
        if emitted >= cap:
            break
        outstanding, days = float(outstanding or 0), int(days or 0)
        d = C.decide(days_overdue=days, outstanding=outstanding,
                     state=states.get(customer), open_promise=promises.get(customer),
                     min_amount=min_amount)
        if not d.allowed:
            continue
        new_id = bus.emit(
            conn, company_id, "invoice.overdue_rung",
            # One event per customer per rung, ever. The ladder is the memory.
            dedupe_key=f"{customer}:rung{d.rung}",
            entity_ref=f"customer:{customer}",
            severity=min(90, 30 + d.rung * 12),
            source="detect.overdue_rung",
            run_id=run_id,
            payload={"customer_name": customer, "outstanding": outstanding,
                     "days_overdue": days, "invoice_count": int(invoices or 0),
                     "rung": d.rung, "rung_label": C.rung(d.rung).label},
        )
        if new_id:
            emitted += 1
    return emitted


def detect_promise_broken(conn, company_id: str, *, run_id: int | None = None,
                          config: dict | None = None) -> int:
    """Promises whose day has come and gone.

    A broken promise is worth more than the missed payment. A customer who is
    simply slow and a customer who agrees a date and ignores it are different
    credit risks, and this is the only place that difference gets recorded.
    """
    from vinayak import collections as C

    result = C.settle_due_promises(conn, company_id)
    emitted = 0
    for broken in result["broken"]:
        new_id = bus.emit(
            conn, company_id, "promise.broken",
            dedupe_key=broken["id"],
            entity_ref=f"customer:{broken['customer_ref']}",
            severity=75,
            source="detect.promise_broken",
            run_id=run_id,
            payload=broken,
        )
        if new_id:
            emitted += 1
    if result["kept"]:
        logger.info("%s: %d promise(s) kept", company_id, len(result["kept"]))
    conn.commit()
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
    "detect.promise_broken": detect_promise_broken,
    "detect.data_stale": detect_data_stale,
    "detect.anomaly": detect_anomaly,
}
