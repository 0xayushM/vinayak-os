"""
model/port.py
──────────────
The ModelPort interface — the single abstraction every layer uses to reach a
language model. Orchestration code (agents, engine) depends on THIS, not on the
Anthropic SDK, so the provider can be swapped without touching callers.

Four responsibilities:
  • chat()            — a tool-use turn (system + messages [+ tools]) → raw response
  • route()           — classify an off-router question into one known intent
  • phrase()          — rewrite validated claims into owner-facing prose
  • rewrite_followup()— resolve a follow-up into a standalone question
plus the tier accessors (fast/smart) and is_active().
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ModelPort(ABC):
    @abstractmethod
    def is_active(self) -> bool:
        """True when a model is configured and reachable."""

    @abstractmethod
    def model_fast(self) -> str:
        """The cheap/fast model id (lookups, routing)."""

    @abstractmethod
    def model_smart(self) -> str:
        """The strong model id (judgement, tool-use, phrasing)."""

    @abstractmethod
    def chat(self, *, system: str, messages: list[dict],
             tools: list[dict] | None = None, model: str | None = None,
             max_tokens: int = 1024) -> Any:
        """One model turn. Returns the provider's raw response object (the caller
        reads .content / .stop_reason). `tools=None` forces a text-only turn."""

    @abstractmethod
    def route(self, question: str, intents: list[tuple[str, str]],
              model: str | None = None) -> str | None:
        ...

    @abstractmethod
    def phrase(self, ans, model: str | None = None, context: dict | None = None,
               retry: bool = False) -> str:
        ...

    @abstractmethod
    def rewrite_followup(self, question: str, history: list[dict],
                         model: str | None = None) -> str | None:
        ...
