"""
agents/native.py
─────────────────
The default orchestration engine: the owned, thin Anthropic tool-use loop
(reasoning/agent.py), wrapped as an AgentRunner. Falls back to the deterministic
engine when no model is configured or a model call fails — that behaviour lives
inside run_agent, so it holds for every caller of this runner.
"""
from __future__ import annotations


class NativeAgentRunner:
    name = "native"

    def run(self, conn, company_id: str, question: str,
            history_turns: list[dict] | None = None) -> dict:
        from vinayak.reasoning.agent import run_agent
        return run_agent(conn, company_id, question, history_turns=history_turns)
