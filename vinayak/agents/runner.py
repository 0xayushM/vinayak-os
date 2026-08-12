"""
reasoning/runner.py
────────────────────
The AgentRunner port — the single seam behind which the orchestration engine
lives (BIDE Part 1A, "the frozen core"). Every way of driving the universal loop
implements ONE interface:

    run(conn, company_id, question, history_turns) -> dict   # a serialised Answer

Today's default implementation is `NativeAgentRunner`, a thin wrapper over the
owned Anthropic tool-use loop in reasoning/agent.py. Tomorrow, a LangGraph or
Google ADK engine is just another class implementing this same interface — see
reasoning/adk_runner.py. Because callers depend only on this port, swapping the
engine touches nothing above it: not the tools, the evidence contract, the
safety spine, memory, or the gates.

Selection is by env so it can be flipped without a code change:

    AGENT_RUNNER = native   (default) | adk

The grounding + numeric guard + confidence gate are NOT re-implemented per
runner — every runner routes its output through reasoning/safety.py.
"""
from __future__ import annotations

import os
from typing import Protocol, runtime_checkable


from vinayak.agents.native import NativeAgentRunner


@runtime_checkable
class AgentRunner(Protocol):
    """The one method every orchestration engine must provide."""

    name: str

    def run(self, conn, company_id: str, question: str,
            history_turns: list[dict] | None = None) -> dict:
        ...


def _make_runner(kind: str) -> AgentRunner:
    kind = (kind or "native").strip().lower()
    if kind == "adk":
        from vinayak.agents.adk import AdkAgentRunner
        return AdkAgentRunner()
    return NativeAgentRunner()


def make_runner(kind: str) -> AgentRunner:
    """Construct a specific runner by name — used by the eval harness to grade a
    chosen engine (e.g. 'native' vs 'adk') independently of the AGENT_RUNNER env."""
    return _make_runner(kind)


def get_runner() -> AgentRunner:
    """The active runner, chosen by AGENT_RUNNER (default 'native')."""
    return _make_runner(os.getenv("AGENT_RUNNER", "native"))
