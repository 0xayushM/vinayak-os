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

def _handle_overdue_rung(conn, company_id: str, event: dict) -> dict:
    """Draft a payment reminder at the rung this customer has reached.

    The rung comes from the event, which got it from `collections.decide` —
    the consumer does not re-derive it. One place decides how firm to be.
    """
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

    level = int(p.get("rung", 1))
    ctx = ToolContext(conn=conn, company_id=company_id, user_id="agent")
    res = execute(ctx, tool, {"customer_ref": customer, "rung": level})

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
    return {"action": action_id, "rung": level, "rung_label": p.get("rung_label"),
            "customer": customer}


def _handle_promise_broken(conn, company_id: str, event: dict) -> dict:
    """A promised payment did not arrive.

    Chasing resumes immediately and one rung higher than the ladder alone
    would give: the customer has now had the conversation and not kept to it,
    which is a different situation from simply being late.
    """
    from vinayak import collections as C
    from vinayak.tools import registry
    from vinayak.tools.action_tools import register_action_tools
    from vinayak.tools.executor import ToolContext, execute

    p = event["payload"]
    customer = p.get("customer_ref")
    if not customer:
        return {"action": None, "reason": "event carries no customer"}

    # The pause the promise created is void the moment it is broken.
    with conn.cursor() as cur:
        cur.execute("""UPDATE collections_state
                          SET paused_until = NULL, pause_reason = NULL, updated_at = NOW()
                        WHERE company_id = %s AND customer_ref = %s""",
                    (company_id, customer))
    conn.commit()

    state = C.get_state(conn, company_id, customer)
    level = min(C.MAX_RUNG, max(2, int(state.get("rung") or 1) + 1))

    register_action_tools()
    tool = registry.get("collections.draft_chase")
    ctx = ToolContext(conn=conn, company_id=company_id, user_id="agent")
    res = execute(ctx, tool, {"customer_ref": customer, "rung": level})
    if res.error:
        return {"action": None, "reason": res.error, "rung": level}
    action_id = res.data.get("action_id")
    if action_id:
        with conn.cursor() as cur:
            cur.execute("UPDATE actions SET event_id = %s WHERE id = %s",
                        (event["id"], action_id))
    return {"action": action_id, "rung": level, "customer": customer,
            "reason": f"promise for {p.get('promised_on')} was not kept"}


def _handle_noted(_conn, _company_id: str, event: dict) -> dict:
    """Events that are worth knowing and not worth automating."""
    kind = event["payload"].get("kind") or event["payload"].get("pipeline")
    return {"action": None,
            "reason": ("recorded for the brief and the Business Brain page; "
                       "no action can safely be automated for this"),
            "kind": kind}


HANDLERS = {
    "invoice.overdue_rung": _handle_overdue_rung,
    "promise.broken": _handle_promise_broken,
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
