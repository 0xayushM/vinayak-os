"""
Tests for the ModelPort (vinayak/model). No network required.

Verifies the seam: get_model() returns a ModelPort, and the agent loop drives the
model through chat() — so orchestration code never touches a raw Anthropic client.
"""
from vinayak.model import ModelPort, AnthropicModel, get_model


def test_get_model_returns_a_modelport_singleton():
    m = get_model()
    assert isinstance(m, ModelPort)
    assert isinstance(m, AnthropicModel)
    assert get_model() is m          # shared instance


def test_anthropic_model_delegates_tier_and_active(monkeypatch):
    import vinayak.reasoning.llm as llm
    monkeypatch.setattr(llm, "is_active", lambda: True)
    monkeypatch.setattr(llm, "model_fast", lambda: "fast-x")
    monkeypatch.setattr(llm, "model_smart", lambda: "smart-x")
    m = AnthropicModel()
    assert m.is_active() is True
    assert m.model_fast() == "fast-x"
    assert m.model_smart() == "smart-x"


def test_chat_raises_clearly_without_a_client(monkeypatch):
    import vinayak.reasoning.llm as llm
    monkeypatch.setattr(llm, "_get_client", lambda: None)
    import pytest
    with pytest.raises(RuntimeError, match="No model configured"):
        AnthropicModel().chat(system="s", messages=[{"role": "user", "content": "hi"}])
