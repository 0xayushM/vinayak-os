"""
reasoning/safety.py
────────────────────
The safety spine — the deterministic honesty layer, extracted into ONE module so
every orchestrator (the owned native loop today; a LangGraph or Google ADK
adapter tomorrow) and every vertical reuse the identical guarantees. Nothing here
calls a model; these are pure functions over text + evidence.

This is the frozen "safety spine" contract from the finalized architecture
(BIDE Part 1A). Three responsibilities:

  • grounded()      — does every money figure in the answer trace to tool evidence?
  • confidence()    — the calibrated label, derived from facts (not the model's
                      self-assessment): CERTAIN / PROBABLE / UNCERTAIN.
  • safe_summary()  — the evidence-only fallback used when the model keeps stating
                      a figure no tool returned (the numeric guard's last resort).

The low-level money tokenizers (_num_tokens / _norm_num) live in engine.py and
are imported here so there is a single normalisation everywhere.
"""
from __future__ import annotations

from vinayak.domain.models import Evidence
from vinayak.domain.money import num_tokens as _num_tokens, norm_num as _norm_num

__all__ = ["grounded", "confidence", "safe_summary", "answer_text"]


def grounded(text: str, evidence: list[Evidence]) -> bool:
    """Every money figure in `text` must trace to a tool's evidence — either its
    rounded display ('₹2.40 Cr') or its exact raw value ('₹2,39,53,022.37'). Both
    are legitimate ways to quote the same tool figure, so both are allowed;
    anything else fails closed and the numeric guard blocks it."""
    allowed: set[str] = set()
    for e in evidence:
        allowed |= _num_tokens(e.display)
        allowed |= _num_tokens(str(e.value))
        if isinstance(e.value, (int, float)) and not isinstance(e.value, bool):
            allowed.add(_norm_num(str(e.value)))
    return all(tok in allowed for tok in _num_tokens(text or ""))


def confidence(is_grounded: bool, evidence: list[Evidence], used_tools: list[str],
               blocked: bool = False) -> str:
    """The calibrated confidence label, derived deterministically:
      • no tool consulted            → UNCERTAIN
      • a figure was blocked/invented → PROBABLE (we fell back)
      • grounded with evidence        → CERTAIN
      • tools used but didn't verify  → PROBABLE
    """
    if not used_tools:
        return "UNCERTAIN"
    if blocked:
        return "PROBABLE"
    if is_grounded and evidence:
        return "CERTAIN"
    return "PROBABLE"


def safe_summary(evidence: list[Evidence]) -> str:
    """A grounded fallback that never surfaces a figure the tools didn't return.
    Used when the model keeps stating an uncited rupee amount even after a
    correction — we answer only from the evidence we actually hold."""
    if not evidence:
        return ("I couldn't find the figures needed to answer that reliably. "
                "Try asking about a specific metric (revenue, outstanding, overdue).")
    seen: set[str] = set()
    parts: list[str] = []
    for e in evidence:
        if e.display in seen:
            continue
        seen.add(e.display)
        parts.append(f"{e.label}: {e.display}")
        if len(parts) >= 6:
            break
    return "Here's what the data shows — " + "; ".join(parts) + "."


def answer_text(resp) -> str:
    """Concatenate the text blocks of an Anthropic-style model response."""
    return "".join(getattr(b, "text", "") for b in getattr(resp, "content", [])
                   if getattr(b, "type", None) == "text").strip()
