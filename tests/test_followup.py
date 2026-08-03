"""Unit tests for multi-turn follow-up detection and rewrite gating."""
from vinayak.reasoning.engine import _looks_followup
from vinayak.reasoning import llm


def test_pronoun_references_are_followups():
    assert _looks_followup("and which of those are overdue?")
    assert _looks_followup("what about them?")
    assert _looks_followup("why?")
    assert _looks_followup("break that down by month")
    assert _looks_followup("the biggest one")


def test_standalone_questions_are_not_followups():
    assert not _looks_followup("who are my top customers this month?")
    assert not _looks_followup("how much stock value am I holding right now?")
    assert not _looks_followup("show me overdue purchase orders for kbrushes")


def test_very_short_fragments_count_as_followups():
    assert _looks_followup("overdue ones")
    assert _looks_followup("since january?")


def test_rewrite_returns_none_without_llm_or_history(monkeypatch):
    # Force the no-LLM path (a dev machine may have a real key in .env).
    monkeypatch.setattr(llm, "_client", None)
    monkeypatch.setattr(llm, "_checked", True)
    assert llm.rewrite_followup("and those?", [{"question": "q", "answer": "a"}]) is None
    # And no history means nothing to resolve against, regardless of LLM.
    assert llm.rewrite_followup("and those?", []) is None
