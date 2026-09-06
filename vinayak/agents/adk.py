"""
agents/adk.py
────────────────────────
Google ADK adapter — a SCAFFOLD implementation of the AgentRunner port
(agents/runner.py). It shows exactly how a framework plugs in behind the seam
without disturbing the frozen core: ADK drives tool selection, but our tools, our
evidence contract, and our safety spine are unchanged, and the output is the same
Answer dict every other runner produces.

This is intentionally inert until you opt in. Selecting it (AGENT_RUNNER=adk)
without installing ADK raises a clear, actionable error rather than crashing.

── Setup ─────────────────────────────────────────────────────────────────────
  1. pip install google-adk litellm
  2. Keep using Claude (so the safety spine's grounding holds) via LiteLLM:
        export AGENT_RUNNER=adk
        export ADK_MODEL="anthropic/claude-sonnet-4-6"      # LiteLlm model id
        export ANTHROPIC_API_KEY=...                        # already set
     (Or use Gemini directly: ADK_MODEL="gemini-2.0-flash" + GOOGLE_API_KEY.)
  3. Run the eval harness against this runner before flipping it on for /ask:
        AGENT_RUNNER=adk PYTHONPATH=. python -m vinayak.eval.harness --runner adk

── Why this is safe to adopt later ───────────────────────────────────────────
  • ADK only chooses which read tools to call. Numbers still come from our tools.
  • Every tool call goes through vinayak.tools.executor.execute → Evidence.
  • The final text is run through vinayak.reasoning.safety (grounding, numeric
    guard, confidence) — identical to the native runner. ADK cannot loosen the
    honesty guarantees.
  • Company scope is injected here, never chosen by the model.
"""
from __future__ import annotations

import json
import logging
import os

from vinayak.reasoning.engine import Answer, Evidence
from vinayak.reasoning import safety
from vinayak.tools import registry
from vinayak.tools.executor import ToolContext, execute
from vinayak.tools.read_tools import register_all

logger = logging.getLogger(__name__)


def _adk_available() -> bool:
    try:
        import google.adk  # noqa: F401
        return True
    except Exception:
        return False


class AdkAgentRunner:
    """AgentRunner backed by Google ADK. Behind the same port as NativeAgentRunner.

    The run() body is the scaffold: it builds ADK FunctionTools from our registry
    (each wrapped so it records Evidence), runs an ADK agent, then finalises
    through the shared safety spine. The ADK session-loop specifics are marked
    with TODO where a live install completes them; everything around them — the
    tool wrapping, evidence capture, and the safety finalisation — is real.
    """

    name = "adk"

    def __init__(self) -> None:
        if not _adk_available():
            raise RuntimeError(
                "AGENT_RUNNER=adk but google-adk is not installed. "
                "Run `pip install google-adk litellm` and set ADK_MODEL "
                "(see agents/adk.py for the setup guide), or unset "
                "AGENT_RUNNER to use the default native runner."
            )

    # ── tool bridge: our Tool registry → ADK FunctionTools ────────────────────
    def _build_tools(self, ctx: ToolContext, evidence_sink: list[Evidence],
                     used_tools: list[str]):
        """Wrap each read tool as a plain callable ADK can use. Each call runs our
        deterministic executor, records the Evidence, and returns the tool data.
        company_id is bound from ctx here — never a model-chosen argument."""
        from google.adk.tools import FunctionTool  # type: ignore

        adk_tools = []
        for tool in registry.all_tools(side_effect="read"):
            def _make(bound_tool):
                def _call(**kwargs) -> dict:
                    result = execute(ctx, bound_tool, dict(kwargs))
                    used_tools.append(bound_tool.name)
                    evidence_sink.extend(result.evidence)
                    if result.error:
                        return {"error": result.error}
                    return result.data
                _call.__name__ = bound_tool.name.replace(".", "_")
                _call.__doc__ = bound_tool.description
                return _call
            adk_tools.append(FunctionTool(_make(tool)))
        return adk_tools

    def _model(self):
        """Keep Claude via LiteLLM by default so the grounding contract holds."""
        model_id = os.getenv("ADK_MODEL", "anthropic/claude-sonnet-4-6")
        if model_id.startswith(("gemini", "vertex")):
            return model_id  # ADK talks to Gemini natively
        from google.adk.models.lite_llm import LiteLlm  # type: ignore
        return LiteLlm(model=model_id)

    def run(self, conn, company_id: str, question: str,
            history_turns: list[dict] | None = None) -> dict:
        from vinayak.reasoning import agent  # reuse the shared system prompt
        register_all()
        ctx = ToolContext(conn=conn, company_id=company_id)
        evidence_all: list[Evidence] = []
        used_tools: list[str] = []

        try:
            from google.adk.agents import LlmAgent  # type: ignore
            tools = self._build_tools(ctx, evidence_all, used_tools)
            adk_agent = LlmAgent(
                name="finance_analyst",
                model=self._model(),
                instruction=agent._system_prompt(conn, company_id),
                tools=tools,
            )
            # TODO(adk): drive a session with google.adk.runners.InMemoryRunner,
            # feed `question` (+ history_turns), and collect the final text. Until
            # that loop is wired against a live install, we surface a clear signal
            # rather than a silent wrong answer.
            text = self._invoke(adk_agent, question, history_turns)
        except NotImplementedError:
            logger.warning("adk_runner: session loop not wired; falling back to native")
            from vinayak.reasoning.agent import run_agent
            return run_agent(conn, company_id, question, history_turns=history_turns)

        # ── the shared safety spine: identical to every other runner ──────────
        if evidence_all and text and not safety.grounded(text, evidence_all):
            text, blocked = safety.safe_summary(evidence_all), True
        else:
            blocked = False
        is_grounded = safety.grounded(text, evidence_all)
        ans = Answer(
            question=question, intent="agent", answer=text,
            confidence=safety.confidence(is_grounded, evidence_all, used_tools, blocked),
            evidence=list(evidence_all), data_used=list(dict.fromkeys(used_tools)),
            gates={"grounded": is_grounded, "tools_used": list(dict.fromkeys(used_tools)),
                   "routed_by": "adk"},
        )
        out = ans.to_dict()
        out["meta"] = {"routed_by": "adk", "ai_active": True,
                       "numeric_guard": "blocked" if blocked else "ok",
                       "grounded": is_grounded}
        return out

    def _invoke(self, adk_agent, question: str, history_turns) -> str:
        """The one piece that needs a live ADK install to complete."""
        raise NotImplementedError(
            "Wire google.adk.runners.InMemoryRunner here once google-adk is installed."
        )
