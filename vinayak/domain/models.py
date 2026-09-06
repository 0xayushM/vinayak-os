"""
domain/models.py
─────────────────
The core value objects every layer shares. These were previously defined inside
reasoning/engine.py, which forced tools, safety, and the runners to import from
the busiest module in the codebase (an inverted dependency that created import
cycles). They live here now, at the bottom of the DAG, with zero dependencies.

Pure data (dataclasses) — no behaviour beyond serialisation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Confidence labels — the calibrated buckets the safety spine assigns.
CERTAIN = "CERTAIN"
PROBABLE = "PROBABLE"
UNCERTAIN = "UNCERTAIN"
CONFIDENCE_LEVELS = (CERTAIN, PROBABLE, UNCERTAIN)


@dataclass
class Evidence:
    """A single figure the brain is allowed to use — the most load-bearing object
    in the system. Grounding, citation, and the numeric guard all stand on it."""
    id: str
    label: str
    value: Any
    display: str


@dataclass
class Claim:
    text: str
    type: str               # 'computed' | 'inference' | 'unknown'
    evidence: list[str] = field(default_factory=list)
    assumption: str | None = None


@dataclass
class Answer:
    question: str
    intent: str
    answer: str
    confidence: str         # CERTAIN | PROBABLE | UNCERTAIN
    claims: list[Claim] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    data_used: list[str] = field(default_factory=list)
    what_i_dont_know: list[str] = field(default_factory=list)
    suggested_fact: dict | None = None      # prompt the owner to teach a fact
    gates: dict = field(default_factory=dict)
    chart: dict | None = None                # {title, unit, items:[{name,value,display}]}

    def to_dict(self) -> dict:
        return {
            "question": self.question, "intent": self.intent, "answer": self.answer,
            "confidence_level": self.confidence,
            "claims": [c.__dict__ for c in self.claims],
            "evidence": [e.__dict__ for e in self.evidence],
            "assumptions": self.assumptions, "data_used": self.data_used,
            "what_i_dont_know": self.what_i_dont_know,
            "suggested_fact": self.suggested_fact, "gates": self.gates,
            "chart": self.chart,
        }
