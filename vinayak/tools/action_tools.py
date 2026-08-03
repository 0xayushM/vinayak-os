"""
tools/action_tools.py
──────────────────────
Layer 7/9 — the first ACTION tool: collections.draft_chase.

An action tool NEVER acts. It composes a proposal (here, a payment-reminder
email) from real, grounded figures and hands it to the executor, which writes it
to the `actions` ledger as status='proposed'. A human then approves it in the
inbox before anything is ever sent. Money and outbound messages never automate.

The message composer is pure (compose_chase) so the wording is unit-testable
without a DB, and every rupee figure it states comes from the canonical AR data
the tool looked up — not from the model.
"""
from __future__ import annotations

from vinayak.reasoning.engine import Evidence, inr
from vinayak.tools import registry
from vinayak.tools.contract import Tool, ToolInput, ToolResult

_TONES = ("gentle", "firm")


def compose_chase(customer: str, outstanding: float, overdue: float,
                  oldest_days: int, tone: str = "gentle") -> tuple[str, str]:
    """Pure, deterministic reminder composer. Returns (subject, body). The amount
    shown is the overdue figure (or outstanding if nothing is past due yet)."""
    tone = tone if tone in _TONES else "gentle"
    amt = inr(overdue if overdue > 0 else outstanding)
    aged = f" (oldest {oldest_days} days)" if oldest_days and oldest_days > 0 else ""
    if tone == "firm":
        subject = f"Payment overdue: {amt} — action needed"
        body = (
            f"Dear {customer},\n\n"
            f"Our records show {amt} overdue on your account{aged}. "
            "Please arrange payment at the earliest, or reply with a date we can "
            "expect it so we can update our records.\n\n"
            "Regards,\nAccounts"
        )
    else:
        subject = f"Gentle reminder: {amt} outstanding"
        body = (
            f"Dear {customer},\n\n"
            f"A gentle reminder that {amt} is currently outstanding on your account{aged}. "
            "If payment is already on its way, please ignore this note — otherwise we'd "
            "appreciate a quick update on timing.\n\n"
            "Warm regards,\nAccounts"
        )
    return subject, body


def _draft_chase(ctx, customer_ref: str, tone: str = "gentle") -> ToolResult:
    with ctx.conn.cursor() as cur:
        cur.execute(
            """SELECT COALESCE(SUM(outstanding_amount), 0),
                      COALESCE(SUM(outstanding_amount) FILTER (WHERE days_overdue > 0), 0),
                      MAX(days_overdue)
               FROM canon_ar_flat
               WHERE company_id = %s AND customer_name = %s""",
            (ctx.company_id, customer_ref),
        )
        row = cur.fetchone()
    outstanding = float(row[0] or 0) if row else 0.0
    overdue = float(row[1] or 0) if row else 0.0
    oldest = int(row[2]) if row and row[2] is not None else 0
    if outstanding <= 0:
        return ToolResult.fail(f"{customer_ref} has nothing outstanding — no reminder needed.")

    subject, body = compose_chase(customer_ref, outstanding, overdue, oldest, tone)
    return ToolResult(
        data={
            "customer": customer_ref, "channel": "email", "tone": tone,
            "outstanding": outstanding, "overdue": overdue, "oldest_days": oldest,
            "subject": subject, "body": body,
            "summary": f"Payment reminder to {customer_ref} — {inr(overdue if overdue > 0 else outstanding)}",
        },
        evidence=[
            Evidence("chase:overdue", "Overdue", overdue, inr(overdue)),
            Evidence("chase:outstanding", "Outstanding", outstanding, inr(outstanding)),
        ],
        quality={"data_fresh": True, "source": "canonical"},
    )


_ACTION_TOOLS: list[Tool] = [
    Tool(
        name="collections.draft_chase",
        description=("Draft a payment reminder to a customer with an overdue balance. "
                     "Proposes only — a human approves in the inbox before anything is sent."),
        inputs={
            "customer_ref": ToolInput(str, "Customer name to remind", required=True),
            "tone": ToolInput(str, "gentle | firm", required=False),
        },
        side_effect="writes",   # → executor proposes to the ledger; gate = 'confirm'
        fn=_draft_chase,
    ),
]


def register_action_tools() -> int:
    """Register action tools (idempotent). Returns count newly registered."""
    n = 0
    for t in _ACTION_TOOLS:
        if registry.get(t.name) is None:
            registry.register(t)
            n += 1
    return n


def action_tool_names() -> list[str]:
    return [t.name for t in _ACTION_TOOLS]
