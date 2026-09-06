"""
model/anthropic.py
───────────────────
The Anthropic implementation of ModelPort. For this stage it delegates the
prompt-heavy operations (route / phrase / rewrite_followup and the tier/client
helpers) to the existing reasoning/llm.py — moving those verbatim into this
module is a later cosmetic step. The important structural win now: `chat()` owns
the `client.messages.create` call, so agents no longer touch the raw client.
"""
from __future__ import annotations

from typing import Any

from vinayak.model.port import ModelPort
from vinayak.reasoning import llm


class AnthropicModel(ModelPort):
    """ModelPort backed by Anthropic's SDK (via reasoning/llm.py's client + prompts)."""

    def is_active(self) -> bool:
        return llm.is_active()

    def model_fast(self) -> str:
        return llm.model_fast()

    def model_smart(self) -> str:
        return llm.model_smart()

    def chat(self, *, system: str, messages: list[dict],
             tools: list[dict] | None = None, model: str | None = None,
             max_tokens: int = 1024) -> Any:
        client = llm._get_client()
        if client is None:
            raise RuntimeError("No model configured (ANTHROPIC_API_KEY unset).")
        kwargs: dict[str, Any] = {
            "model": model or self.model_smart(),
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        return client.messages.create(**kwargs)

    def route(self, question, intents, model=None):
        return llm.route(question, intents, model=model)

    def phrase(self, ans, model=None, context=None, retry=False):
        return llm.phrase(ans, model=model, context=context, retry=retry)

    def rewrite_followup(self, question, history, model=None):
        return llm.rewrite_followup(question, history, model=model)


_model: ModelPort | None = None


def get_model() -> ModelPort:
    """The shared ModelPort instance."""
    global _model
    if _model is None:
        _model = AnthropicModel()
    return _model
