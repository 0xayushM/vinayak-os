"""
tools/registry.py
──────────────────
The catalogue of every declared tool. The agent (Layer 8) is handed a filtered
view of this registry per request; MCP later exposes the same registry to
external clients — which is why nothing here is Anthropic-specific except the
schema emitter on the Tool itself.
"""
from __future__ import annotations

from vinayak.tools.contract import Tool

_REGISTRY: dict[str, Tool] = {}


def register(t: Tool) -> None:
    if t.name in _REGISTRY:
        raise ValueError(f"Duplicate tool name: {t.name}")
    _REGISTRY[t.name] = t


def get(name: str) -> Tool | None:
    """Look up by canonical name ('ar.get_summary') or SDK name ('ar__get_summary')."""
    return _REGISTRY.get(name) or _REGISTRY.get(name.replace("__", "."))


def all_tools(side_effect: str | None = None) -> list[Tool]:
    ts = list(_REGISTRY.values())
    if side_effect:
        ts = [t for t in ts if t.side_effect == side_effect]
    return sorted(ts, key=lambda t: t.name)


def anthropic_schemas(read_only: bool = True) -> list[dict]:
    """Tool list for a model call. v0 hands the model READ tools only; action
    tools join in Wave 2 (and even then they only propose)."""
    ts = all_tools("read") if read_only else all_tools()
    return [t.anthropic_schema() for t in ts]


def clear() -> None:
    """Test helper."""
    _REGISTRY.clear()
