"""
tools/contract.py
──────────────────
The tool contract — the one abstraction Layers 7–10 are built on
(docs/TOOL_CATALOG.md, docs/V0_FINANCE_SPEC.md).

A tool is a plain Python function plus declared metadata:

    @tool(
        name="ar.get_summary",
        description="Total receivables: outstanding, overdue, aging buckets, top exposures.",
        inputs={"period_days": ToolInput(int, "Window in days", required=False)},
        side_effect="read",
    )
    def get_ar_summary_tool(ctx, period_days=None) -> ToolResult: ...

Design rules (non-negotiable):
  • side_effect ∈ {read, writes, moves_money, files_regulator}. Only `read` tools
    may execute inline. Everything else PROPOSES — the executor writes an
    `actions` row and the approval inbox executes it later. No tool both reads
    the world and changes it.
  • Every numeric fact a tool returns is tagged Evidence, so the same
    validate/numeric-guard spine that protects Ask protects the agent.
  • quality signals are plain booleans/floats the (deterministic) confidence
    gate reads — the model never grades itself.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from vinayak.reasoning.engine import Evidence  # single Evidence type everywhere

SIDE_EFFECTS = ("read", "writes", "moves_money", "files_regulator")


@dataclass
class ToolInput:
    type: type
    description: str
    required: bool = True

    @property
    def json_type(self) -> str:
        return {int: "integer", float: "number", bool: "boolean"}.get(self.type, "string")


@dataclass
class ToolResult:
    """What every tool hands back to the loop."""
    data: dict[str, Any]                          # the structured payload
    evidence: list[Evidence] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)   # gate signals (data_fresh, …)
    error: str | None = None

    @classmethod
    def fail(cls, message: str) -> "ToolResult":
        return cls(data={}, error=message)


@dataclass
class Tool:
    name: str
    description: str
    inputs: dict[str, ToolInput]
    side_effect: str
    fn: Callable[..., ToolResult]

    def anthropic_schema(self) -> dict:
        """The tool as the Anthropic SDK expects it."""
        props = {
            k: {"type": inp.json_type, "description": inp.description}
            for k, inp in self.inputs.items()
        }
        return {
            "name": self.name.replace(".", "__"),   # SDK names: [a-zA-Z0-9_-]
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": props,
                "required": [k for k, i in self.inputs.items() if i.required],
            },
        }

    @property
    def is_read(self) -> bool:
        return self.side_effect == "read"


def tool(name: str, description: str, side_effect: str,
         inputs: dict[str, ToolInput] | None = None):
    """Decorator: declare a function as a Tool and register it."""
    if side_effect not in SIDE_EFFECTS:
        raise ValueError(f"side_effect must be one of {SIDE_EFFECTS}, got {side_effect!r}")

    def wrap(fn: Callable[..., ToolResult]) -> Tool:
        t = Tool(name=name, description=description,
                 inputs=inputs or {}, side_effect=side_effect, fn=fn)
        from vinayak.tools.registry import register
        register(t)
        return t

    return wrap
