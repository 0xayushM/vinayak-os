"""
Unit tests for the first action tool (collections.draft_chase). No DB required.

Two guarantees matter: the tool only ever PROPOSES (side_effect='writes' → the
executor gates it), and the reminder wording is grounded — the amount it states
is the figure we pass in, formatted, not invented.
"""
from vinayak.tools import registry
from vinayak.tools.action_tools import compose_chase, register_action_tools


def setup_function():
    registry.clear()


def test_draft_chase_is_a_gated_write_tool():
    register_action_tools()
    t = registry.get("collections.draft_chase")
    assert t is not None
    assert t.side_effect == "writes"      # never 'read' → never executes inline
    assert not t.is_read
    assert "customer_ref" in t.inputs and t.inputs["customer_ref"].required


def test_register_action_tools_idempotent():
    assert register_action_tools() == 1
    assert register_action_tools() == 0


def test_gentle_tone_wording_and_amount():
    subject, body = compose_chase("Dev Colour", outstanding=6080000, overdue=6080000,
                                  oldest_days=82, tone="gentle")
    assert "gentle reminder" in subject.lower()
    assert "Dev Colour" in body
    assert "₹60.80L" in body          # grounded amount, compact
    assert "oldest 82 days" in body


def test_firm_tone_is_firmer():
    subject, body = compose_chase("Acme", outstanding=500000, overdue=500000,
                                  oldest_days=120, tone="firm")
    assert "overdue" in subject.lower()
    assert "at the earliest" in body


def test_uses_outstanding_when_nothing_overdue_yet():
    subject, body = compose_chase("NewCo", outstanding=100000, overdue=0,
                                  oldest_days=0, tone="gentle")
    assert "₹1.00L" in body
    assert "oldest" not in body        # no aging line when not overdue


def test_unknown_tone_falls_back_to_gentle():
    subject, _ = compose_chase("X", 1000, 1000, 0, tone="aggressive")
    assert "reminder" in subject.lower()
