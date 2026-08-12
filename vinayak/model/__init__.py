"""
vinayak.model
─────────────
The model boundary. High-level code (agents, engine) depends on the ModelPort
interface, never on the raw Anthropic client — so the model provider is swappable
and the client stops leaking into the orchestration code.
"""
from vinayak.model.port import ModelPort
from vinayak.model.anthropic import AnthropicModel, get_model

__all__ = ["ModelPort", "AnthropicModel", "get_model"]
