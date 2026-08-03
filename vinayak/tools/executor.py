"""
tools/executor.py
──────────────────
Runs tools under the safety rules. The single choke-point between "the model
wants to do X" and "X happens".

  • read tools  → execute inline, return ToolResult (evidence + quality).
  • non-read    → NEVER execute. The proposal is written to the `actions`
                  ledger (status='proposed', gate per side_effect) and a
                  reference is returned so the model can tell the user it is
                  queued. The approval inbox — a human — executes it later.
  • every call is idempotency-checked against the ledger for repeat proposals.

The deterministic confidence gate (Wave 2+) plugs in here, reading each tool's
side_effect and the ToolResult.quality signals — never the model's opinion.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from vinayak.tools.contract import Tool, ToolResult

logger = logging.getLogger(__name__)

# side_effect → gate. moves_money / files_regulator are ALWAYS 'human'
# (a person initiates execution), 'writes' is 'confirm' (approval inbox).
GATE_FOR = {
    "read": "auto",
    "writes": "confirm",
    "moves_money": "human",
    "files_regulator": "human",
}

# Per-tool idempotency window (days) for repeat proposals on the same entity.
IDEMPOTENCY_DAYS_DEFAULT = 5


@dataclass
class ToolContext:
    """Everything a tool may need, injected — tools never open their own conns."""
    conn: Any
    company_id: str
    user_id: str | None = None


def execute(ctx: ToolContext, tool: Tool, args: dict) -> ToolResult:
    """Run (or propose) a tool call. Always returns a ToolResult."""
    args = _validate_args(tool, args)
    if isinstance(args, ToolResult):        # validation error
        return args

    if tool.is_read:
        try:
            return tool.fn(ctx, **args)
        except Exception as exc:  # noqa: BLE001 — a tool bug must not kill the loop
            logger.exception("tool %s failed", tool.name)
            return ToolResult.fail(f"{tool.name} failed: {exc}")

    # ── non-read: propose, never execute ────────────────────────────────────
    entity_ref = args.get("entity_ref") or args.get("customer_ref") or None
    dup = _recent_duplicate(ctx, tool, entity_ref)
    if dup:
        return ToolResult.fail(
            f"Not proposed: an identical {tool.name} action for {entity_ref} "
            f"already exists from {dup} (idempotency guard)."
        )

    # The tool fn BUILDS the proposal payload (e.g. drafts the email) but the
    # executor owns writing it to the ledger.
    try:
        draft = tool.fn(ctx, **args)
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool %s draft failed", tool.name)
        return ToolResult.fail(f"{tool.name} failed: {exc}")
    if draft.error:
        return draft

    gate = GATE_FOR[tool.side_effect]
    with ctx.conn.cursor() as cur:
        cur.execute(
            """INSERT INTO actions (company_id, tool_name, entity_ref, payload,
                                    status, gate, proposed_by)
               VALUES (%s, %s, %s, %s, 'proposed', %s, %s)
               RETURNING id""",
            (ctx.company_id, tool.name, entity_ref,
             json.dumps(draft.data, default=str), gate,
             ctx.user_id or "agent"),
        )
        action_id = str(cur.fetchone()[0])
    ctx.conn.commit()

    return ToolResult(
        data={"queued": True, "action_id": action_id, "gate": gate,
              "summary": draft.data.get("summary", tool.name)},
        evidence=draft.evidence, quality=draft.quality,
    )


# ── helpers ───────────────────────────────────────────────────────────────────
def _validate_args(tool: Tool, args: dict) -> dict | ToolResult:
    clean: dict = {}
    for k, spec in tool.inputs.items():
        if k not in args or args[k] is None:
            if spec.required:
                return ToolResult.fail(f"{tool.name}: missing required input '{k}'")
            continue
        v = args[k]
        try:
            clean[k] = spec.type(v) if not isinstance(v, spec.type) else v
        except (TypeError, ValueError):
            return ToolResult.fail(f"{tool.name}: input '{k}' must be {spec.type.__name__}")
    unknown = set(args) - set(tool.inputs)
    if unknown:
        return ToolResult.fail(f"{tool.name}: unknown inputs {sorted(unknown)}")
    return clean


def _recent_duplicate(ctx: ToolContext, tool: Tool, entity_ref: str | None):
    """Any proposed/approved/executed action for the same tool+entity recently?"""
    if entity_ref is None:
        return None
    with ctx.conn.cursor() as cur:
        cur.execute(
            """SELECT created_at::date FROM actions
               WHERE company_id = %s AND tool_name = %s AND entity_ref = %s
                 AND status IN ('proposed', 'approved', 'executed')
                 AND created_at > NOW() - make_interval(days => %s)
               ORDER BY created_at DESC LIMIT 1""",
            (ctx.company_id, tool.name, entity_ref, IDEMPOTENCY_DAYS_DEFAULT),
        )
        row = cur.fetchone()
    return row[0] if row else None
