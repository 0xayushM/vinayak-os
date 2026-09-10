"""
brain/consumer.py
──────────────────
Reads pending events and decides what, if anything, to do about each one.

The honest shape of this file is worth stating up front: only one of the
three event types produces an action today, and that is correct rather than
incomplete. An overdue invoice has an obvious, safe, reversible response —
draft a reminder for a person to approve. A stale feed and an anomaly do not:
nobody wants the brain "fixing" a pipeline or writing off negative stock on
its own. Those events are recorded, surfaced on the Business Brain page and
in the morning brief, and closed with the reason they produced no action.

Writing that reason down is the point. An event that was deliberately left
alone and an event the consumer silently dropped look identical from the
outside, and only one of them is a bug.

Every action here goes through tools/executor.execute, which means it lands
in the ledger as 'proposed' and waits for a human. The consumer has no way to
send anything, by construction — it holds no send tool.
"""
from __future__ import annotations

import logging

from vinayak.brain import bus

logger = logging.getLogger(__name__)

# Rung → the tone the reminder is written in. The ladder is the product
# decision: the fourth letter to a customer should not read like the first.
TONE_FOR_RUNG = {7: "gentle", 30: "gentle", 60: "firm", 90: "firm"}


def _handle_overdue_rung(conn, company_id: str, event: dict) -> dict:
    """Draft a payment reminder at the tone this rung calls for."""
    from vinayak.tools import registry
    from vinayak.tools.action_tools import register_action_tools
    from vinayak.tools.executor import ToolContext, execute

    register_action_tools()
    tool = registry.get("collections.draft_chase")
    if tool is None:                              # pragma: no cover — registry bug
        return {"action": None, "reason": "collections.draft_chase is not registered"}

    p = event["payload"]
    customer = p.get("customer_name")
    if not customer:
        return {"action": None, "reason": "event carries no customer"}

    tone = TONE_FOR_RUNG.get(int(p.get("rung", 30)), "gentle")
    ctx = ToolContext(conn=conn, company_id=company_id, user_id="agent")
    res = execute(ctx, tool, {"customer_ref": customer, "tone": tone})

    if res.error:
        # The commonest "error" here is the executor's own idempotency guard —
        # this customer was chased days ago and should not be chased again.
        # That is the guard working, so it is recorded, not logged as a fault.
        return {"action": None, "reason": res.error}

    action_id = res.data.get("action_id")
    if action_id:
        with conn.cursor() as cur:
            cur.execute("UPDATE actions SET event_id = %s WHERE id = %s",
                        (event["id"], action_id))
    return {"action": action_id, "tone": tone, "rung": p.get("rung"),
            "customer": customer}


def _handle_noted(_conn, _company_id: str, event: dict) -> dict:
    """Events that are worth knowing and not worth automating."""
    kind = event["payload"].get("kind") or event["payload"].get("pipeline")
    return {"action": None,
            "reason": ("recorded for the brief and the Business Brain page; "
                       "no action can safely be automated for this"),
            "kind": kind}


HANDLERS = {
    "invoice.overdue_rung": _handle_overdue_rung,
    "data.stale": _handle_noted,
    "anomaly.detected": _handle_noted,
}


def consume(conn, company_id: str, *, limit: int = 50) -> dict:
    """Process one batch of pending events. Returns counts for the run log.

    One event's failure never stops the batch: it is left pending and picked
    up on the next pass, which is the right behaviour for a transient DB or
    network problem and harmless for a permanent one (it ages out after
    bus.MAX_EVENT_AGE_HOURS).
    """
    expired = bus.expire_stale(conn, company_id)
    events = bus.pending(conn, company_id, limit=limit)

    processed = 0
    actions = 0
    failures = 0
    for event in events:
        handler = HANDLERS.get(event["event_type"])
        if handler is None:
            bus.mark_processed(conn, event["id"], by="consumer",
                               outcome={"reason": "no handler for this event type"})
            processed += 1
            continue
        try:
            outcome = handler(conn, company_id, event)
        except Exception as exc:  # noqa: BLE001 — one bad event must not stop the rest
            logger.exception("consumer: event %s failed", event["id"])
            failures += 1
            conn.rollback()
            continue
        bus.mark_processed(conn, event["id"], by="consumer", outcome=outcome)
        conn.commit()
        processed += 1
        if outcome.get("action"):
            actions += 1

    return {"seen": len(events), "processed": processed, "actions_proposed": actions,
            "failures": failures, "expired": expired}
