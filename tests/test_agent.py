"""
Unit tests for the agent core (Layer 8) — no model or DB required.

We test the honesty helpers (grounding + confidence) and drive the full tool-use
loop with a fake Anthropic client and a fake read tool, so the dispatch →
evidence → grounded-finalise path is exercised end to end.
"""
from vinayak.reasoning.engine import Evidence
from vinayak.reasoning import agent
from vinayak.tools import registry
from vinayak.tools.contract import Tool, ToolResult


def setup_function():
    registry.clear()


# ── pure helpers ──────────────────────────────────────────────────────────────
def test_grounded_accepts_tool_figures():
    ev = [Evidence("x:out", "Outstanding", 2100000, "₹21.00 L")]
    assert agent._grounded("Your outstanding is ₹21.00 L.", ev) is True


def test_grounded_rejects_invented_figure():
    ev = [Evidence("x:out", "Outstanding", 2100000, "₹21.00 L")]
    assert agent._grounded("You also owe ₹99.00 Cr elsewhere.", ev) is False


def test_grounded_true_when_no_numbers():
    assert agent._grounded("Things look steady overall.", []) is True


def test_grounded_accepts_exact_raw_value():
    """The model may quote the precise tool value, not just its rounded display."""
    ev = [Evidence("ar:out", "Outstanding", 23953022.37, "₹2.40 Cr")]
    assert agent._grounded("Your outstanding is ₹2,39,53,022.37.", ev) is True
    assert agent._grounded("Your outstanding is ₹2.40 Cr.", ev) is True     # display form
    assert agent._grounded("Your outstanding is ₹2.4 Cr.", ev) is True      # phrasing variant
    assert agent._grounded("Your outstanding is ₹99,99,999.", ev) is False  # invented


def test_confidence_levels():
    ev = [Evidence("a", "A", 1, "₹1")]
    assert agent._confidence(True, ev, ["finance.get_overview"]) == "CERTAIN"
    assert agent._confidence(False, ev, ["finance.get_overview"]) == "PROBABLE"
    assert agent._confidence(True, [], []) == "UNCERTAIN"     # no tool used


# ── full loop with a fake model + fake tool ───────────────────────────────────
class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)

class _Resp:
    def __init__(self, stop_reason, content):
        self.stop_reason = stop_reason
        self.content = content

class _FakeMessages:
    def __init__(self, script):
        self.script = script
        self.calls = 0
    def create(self, **kwargs):
        r = self.script[self.calls]
        self.calls += 1
        return r

class _FakeClient:
    def __init__(self, script):
        self.messages = _FakeMessages(script)


def _register_fake_tool():
    def fn(ctx, **kw):
        return ToolResult(
            data={"outstanding": 2100000, "stale": False},
            evidence=[Evidence("fake.get_x:outstanding", "Outstanding", 2100000, "₹21.00 L")],
            quality={"data_fresh": True},
        )
    registry.register(Tool(name="fake.get_x", description="fake", inputs={},
                           side_effect="read", fn=fn))


def test_agent_loop_calls_tool_then_grounds_answer():
    _register_fake_tool()
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="t1", name="fake.get_x", input={})]),
        _Resp("end_turn", [_Block(type="text", text="Your outstanding is ₹21.00 L.")]),
    ]
    out = agent.run_agent(conn=None, company_id="acme", question="how much is owed?",
                          client=_FakeClient(script))
    assert out["confidence_level"] == "CERTAIN"
    assert "fake.get_x" in out["data_used"]
    assert out["gates"]["grounded"] is True
    assert "₹21.00 L" in out["answer"]


def test_agent_blocks_invented_number_when_correction_unavailable():
    """Model invents a figure and the correction call can't run (script exhausted →
    treated as a failed model call): we must NOT surface the invented number, and
    fall back to the evidence-only summary."""
    _register_fake_tool()
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="t1", name="fake.get_x", input={})]),
        _Resp("end_turn", [_Block(type="text", text="You are owed ₹5.00 Cr.")]),  # not from the tool
    ]
    out = agent.run_agent(conn=None, company_id="acme", question="how much is owed?",
                          client=_FakeClient(script))
    assert "₹5.00 Cr" not in out["answer"]         # the invented figure is blocked
    assert "₹21.00 L" in out["answer"]             # real evidence is surfaced instead
    assert out["meta"]["numeric_guard"] == "blocked"
    assert out["confidence_level"] == "PROBABLE"


def test_agent_answer_without_tools_is_uncertain():
    script = [_Resp("end_turn", [_Block(type="text", text="I can't tell without more data.")])]
    out = agent.run_agent(conn=None, company_id="acme", question="hi",
                          client=_FakeClient(script))
    assert out["data_used"] == []
    assert out["confidence_level"] == "UNCERTAIN"


# ── the numeric guard: retry, then safe fallback ──────────────────────────────
def test_agent_retry_recovers_when_correction_fixes_the_figure():
    """Model invents a figure, gets corrected, then quotes the real one → CERTAIN."""
    _register_fake_tool()
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="t1", name="fake.get_x", input={})]),
        _Resp("end_turn", [_Block(type="text", text="You are owed ₹5.00 Cr.")]),   # invented
        _Resp("end_turn", [_Block(type="text", text="Your outstanding is ₹21.00 L.")]),  # corrected
    ]
    out = agent.run_agent(conn=None, company_id="acme", question="how much is owed?",
                          client=_FakeClient(script))
    assert out["gates"]["grounded"] is True
    assert out["confidence_level"] == "CERTAIN"
    assert "₹5.00 Cr" not in out["answer"]        # the invented figure never shows
    assert "₹21.00 L" in out["answer"]
    assert out["meta"]["numeric_guard"] == "ok"


def test_agent_blocks_and_falls_back_when_model_keeps_inventing():
    """Model invents both times → we block it and answer from evidence only."""
    _register_fake_tool()
    script = [
        _Resp("tool_use", [_Block(type="tool_use", id="t1", name="fake.get_x", input={})]),
        _Resp("end_turn", [_Block(type="text", text="You are owed ₹5.00 Cr.")]),   # invented
        _Resp("end_turn", [_Block(type="text", text="Actually it's ₹9.00 Cr.")]),  # invented again
    ]
    out = agent.run_agent(conn=None, company_id="acme", question="how much is owed?",
                          client=_FakeClient(script))
    assert "₹5.00 Cr" not in out["answer"]        # neither invented figure survives
    assert "₹9.00 Cr" not in out["answer"]
    assert "₹21.00 L" in out["answer"]            # the real evidence is surfaced
    assert out["meta"]["numeric_guard"] == "blocked"
    assert out["confidence_level"] == "PROBABLE"


def test_should_use_respects_opt_out(monkeypatch):
    # A model being available makes the agent the default…
    monkeypatch.setattr(agent, "agent_available", lambda: True)
    monkeypatch.delenv("AGENT_MODE", raising=False)
    assert agent.should_use() is True
    # …unless explicitly disabled.
    monkeypatch.setenv("AGENT_MODE", "0")
    assert agent.should_use() is False
    # And with no model, the engine answers regardless.
    monkeypatch.setattr(agent, "agent_available", lambda: False)
    monkeypatch.delenv("AGENT_MODE", raising=False)
    assert agent.should_use() is False
