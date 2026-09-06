"""
Tests for the AgentRunner port (agents/runner.py) and the standalone safety
spine (reasoning/safety.py). No model or DB required.

The point of these tests is the seam: callers depend only on `get_runner().run`,
and every runner routes through the same safety functions — so an orchestrator
swap can never change the honesty guarantees.
"""
import os

import pytest

from vinayak.reasoning import safety
from vinayak.agents import runner
from vinayak.reasoning.engine import Evidence


# ── the safety spine ──────────────────────────────────────────────────────────
def test_safety_grounded_accepts_display_and_raw_value():
    ev = [Evidence("ar:out", "Outstanding", 23953022.37, "₹2.40 Cr")]
    assert safety.grounded("Owed: ₹2.40 Cr.", ev) is True          # display
    assert safety.grounded("Owed: ₹2,39,53,022.37.", ev) is True   # exact raw value
    assert safety.grounded("Owed: ₹5.00 Cr.", ev) is False         # invented


def test_safety_confidence_levels():
    ev = [Evidence("a", "A", 1, "₹1")]
    assert safety.confidence(True, ev, ["finance.get_overview"]) == "CERTAIN"
    assert safety.confidence(False, ev, ["finance.get_overview"]) == "PROBABLE"
    assert safety.confidence(True, ev, ["x"], blocked=True) == "PROBABLE"
    assert safety.confidence(True, [], []) == "UNCERTAIN"


def test_safety_safe_summary_only_uses_evidence():
    ev = [Evidence("ar:out", "Outstanding", 2100000, "₹21.00 L")]
    out = safety.safe_summary(ev)
    assert "₹21.00 L" in out
    assert safety.grounded(out, ev) is True         # the fallback is itself grounded
    assert "couldn't find" in safety.safe_summary([])  # empty-evidence path


def test_agent_still_exposes_safety_via_aliases():
    """agent.py delegates to the spine; the old names must still resolve so the
    loop and existing tests keep working."""
    from vinayak.reasoning import agent
    assert agent._grounded is safety.grounded
    assert agent._confidence is safety.confidence


# ── the runner port ───────────────────────────────────────────────────────────
def test_default_runner_is_native(monkeypatch):
    monkeypatch.delenv("AGENT_RUNNER", raising=False)
    r = runner.get_runner()
    assert r.name == "native"
    assert isinstance(r, runner.AgentRunner)   # satisfies the port


def test_native_runner_delegates_to_run_agent(monkeypatch):
    calls = {}
    def fake_run_agent(conn, company_id, question, history_turns=None):
        calls.update(company_id=company_id, question=question)
        return {"answer": "ok", "confidence_level": "CERTAIN"}
    import vinayak.reasoning.agent as agent_mod
    monkeypatch.setattr(agent_mod, "run_agent", fake_run_agent)
    out = runner.NativeAgentRunner().run(conn=None, company_id="acme", question="hi?")
    assert out["answer"] == "ok"
    assert calls == {"company_id": "acme", "question": "hi?"}


def test_harness_grades_via_runner(monkeypatch):
    """The eval harness can grade a runner's live output, not just the engine."""
    from vinayak.eval import harness
    import vinayak.agents.runner as R

    class _FakeRunner:
        name = "fake"
        def run(self, conn, cid, q, history_turns=None):
            return {"answer": "Revenue is ₹5.00 L.", "intent": "agent",
                    "confidence_level": "CERTAIN", "claims": [], "evidence": [],
                    "gates": {"grounded": True}}

    monkeypatch.setattr(R, "make_runner", lambda name: _FakeRunner())
    monkeypatch.setattr(harness, "_seed", lambda *a, **k: [])
    monkeypatch.setattr(harness, "_cleanup", lambda *a, **k: None)

    case = {"id": "t1", "q": "revenue?", "companies": ["acme"]}
    res = harness._check_case(None, "acme", case, runner_name="fake")
    assert res["passed"] is True
    assert res["intent"] == "agent"        # routing not graded for a runner


def test_harness_flags_ungrounded_agent_answer(monkeypatch):
    """An agent answer whose grounding gate failed (and isn't a refusal) is a
    hallucination signal — the ship-gate must catch it."""
    from vinayak.eval import harness
    import vinayak.agents.runner as R

    class _BadRunner:
        name = "bad"
        def run(self, conn, cid, q, history_turns=None):
            return {"answer": "Revenue is ₹9.99 Cr.", "intent": "agent",
                    "confidence_level": "PROBABLE", "claims": [], "evidence": [],
                    "gates": {"grounded": False}}

    monkeypatch.setattr(R, "make_runner", lambda name: _BadRunner())
    monkeypatch.setattr(harness, "_seed", lambda *a, **k: [])
    monkeypatch.setattr(harness, "_cleanup", lambda *a, **k: None)

    case = {"id": "t2", "q": "revenue?", "companies": ["acme"]}
    res = harness._check_case(None, "acme", case, runner_name="bad")
    assert res["checks"]["no_unsupported"] is False
    assert res["passed"] is False


def test_adk_runner_selected_without_install_is_clear(monkeypatch):
    monkeypatch.setenv("AGENT_RUNNER", "adk")
    # If google-adk isn't installed, selecting it must raise an actionable error,
    # not fail silently. (If it IS installed in some env, just skip.)
    from vinayak.agents.adk import _adk_available
    if _adk_available():
        pytest.skip("google-adk is installed in this environment")
    with pytest.raises(RuntimeError, match="google-adk is not installed"):
        runner.get_runner()
