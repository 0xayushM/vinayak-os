"""
reasoning/llm.py
─────────────────
The Claude layer. It does TWO safe jobs and nothing else:

  1. route()   — when the keyword router can't classify a question, Claude picks
                 the right intent from a fixed list (or says "none"). This widens
                 coverage to phrasings we didn't hardcode.
  2. phrase()  — rewrites the final answer prose from the ALREADY-VALIDATED claims.
                 It is handed only the claims + their tags, never the database, so
                 it physically cannot introduce a number that wasn't retrieved.

Numbers and the validation gate stay deterministic with or without Claude. If no
key (or SDK) is present, both functions no-op and the engine runs deterministically.

Enable by setting ANTHROPIC_API_KEY (and optionally ANTHROPIC_MODEL) in .env.
"""
from __future__ import annotations

import os

_client = None
_checked = False


def _get_client():
    """Lazy singleton. Returns an Anthropic client, or None if unavailable."""
    global _client, _checked
    if _checked:
        return _client
    _checked = True
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        _client = anthropic.Anthropic(api_key=key)
    except Exception:
        _client = None
    return _client


def is_active() -> bool:
    return _get_client() is not None


def model_fast() -> str:
    return os.environ.get("ANTHROPIC_MODEL_FAST", "claude-haiku-4-5")


def model_smart() -> str:
    return os.environ.get("ANTHROPIC_MODEL", os.environ.get("ANTHROPIC_MODEL_SMART", "claude-sonnet-4-6"))


# ── 1. Routing fallback ───────────────────────────────────────────────────────
_ROUTE_SYSTEM = (
    "You classify an Indian SMB owner's business question into exactly one intent id "
    "from the list provided. Reply with ONLY the intent id, lowercase, nothing else. "
    "If none fit, reply exactly: none."
)


def route(question: str, intents: list[tuple[str, str]], model: str | None = None) -> str | None:
    """Map a question to one known intent id using Claude. Returns the id or None.
    `intents` is a list of (id, short_description)."""
    client = _get_client()
    if client is None:
        return None
    catalog = "\n".join(f"- {i}: {desc}" for i, desc in intents)
    try:
        resp = client.messages.create(
            model=model or model_fast(), max_tokens=20,
            system=_ROUTE_SYSTEM,
            messages=[{"role": "user", "content": f"Intents:\n{catalog}\n\nQuestion: {question}\n\nIntent id:"}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content).strip().lower()
        valid = {i for i, _ in intents}
        return text if text in valid else None
    except Exception:
        return None


# ── 2. Phrasing ───────────────────────────────────────────────────────────────
_PHRASE_SYSTEM = (
    "You are a sharp management consultant and chartered accountant advising the owner of "
    "an Indian SMB. You are given: the business context, any durable facts the owner has "
    "confirmed, and a set of CLAIMS already computed and validated from the company's data "
    "(each tagged computed / inference / unknown) plus a confidence level.\n\n"
    "Your job is not to restate the numbers — it is to turn them into a useful, decision-ready "
    "answer: what the data says, what it means for this business, and what to do next.\n\n"
    "FORMAT (Markdown):\n"
    "1. One bold headline sentence that directly answers the question.\n"
    "2. The supporting detail — use a Markdown table or bullet list whenever several items are "
    "involved (customers, products, vendors, buckets); never cram a list into a sentence.\n"
    "3. A short '**What this means / what to do**' line with one concrete, practical recommendation, "
    "informed by the business context (industry, healthy margin, seasonality) when relevant.\n\n"
    "HARD RULES (non-negotiable):\n"
    "• Every RUPEE amount you state must be copied exactly from the claims/context — never invent, "
    "round, or recompute a rupee figure. Do NOT add two or more amounts together or state any "
    "combined / subtotal / 'top two' rupee figure; only quote amounts exactly as given.\n"
    "• In your recommendation, stay QUALITATIVE — say 'smaller / mid-sized accounts', not an invented "
    "rupee range like '₹3–8L'. Do not put any rupee figure in advice unless it came from the data.\n"
    "• You may reference a percentage share to make a point, but don't present invented precision.\n"
    "• Keep inferences hedged ('looks like', 'assuming'). If confidence is UNCERTAIN, be honest you "
    "can't answer reliably and state exactly what data you'd need.\n"
    "• Indian number style (lakh/crore) exactly as written. No preamble, no sign-off."
)


def _context_block(context: dict | None) -> str:
    if not context:
        return ""
    bits = []
    if context.get("industry"):
        bits.append(f"Industry: {context['industry']}"
                    + (f" ({context['sub_vertical']})" if context.get("sub_vertical") else ""))
    if context.get("healthy_margin_pct") is not None:
        bits.append(f"Healthy margin benchmark: {context['healthy_margin_pct']}%")
    if context.get("seasonality"):
        bits.append(f"Seasonality: {context['seasonality']}")
    if context.get("fiscal_year_start"):
        bits.append(f"Fiscal year starts: {context['fiscal_year_start']}")
    facts = context.get("facts") or []
    block = ""
    if bits:
        block += "Business context:\n" + "\n".join(f"- {b}" for b in bits) + "\n"
    if facts:
        block += "Owner-confirmed facts:\n" + "\n".join(f"- {f}" for f in facts) + "\n"
    return block


def phrase(ans, model: str | None = None, context: dict | None = None, retry: bool = False) -> str:
    """Rephrase ans.answer as an analyst from validated claims + brand context.
    `retry=True` adds a correction nudge (used after the numeric guard blocks a
    draft that combined/invented a rupee figure). Falls back to ans.answer on error."""
    client = _get_client()
    if client is None:
        return ans.answer
    claims_txt = "\n".join(
        f"- [{c.type}] {c.text}" + (f" (assumption: {c.assumption})" if c.assumption else "")
        for c in ans.claims
    )
    user = (
        _context_block(context)
        + f"\nConfidence: {ans.confidence}\nClaims (the only numbers you may use):\n{claims_txt}\n"
        + (f"What I don't know: {'; '.join(ans.what_i_dont_know)}\n" if ans.what_i_dont_know else "")
        + ("\nIMPORTANT: a previous draft stated a rupee figure that is NOT in the claims above "
           "(you combined or invented an amount). Rewrite using ONLY the exact amounts listed — "
           "do not add, subtotal, or combine any rupee figures.\n" if retry else "")
        + "\nWrite the owner-facing analyst answer."
    )
    try:
        resp = client.messages.create(
            model=model or model_fast(), max_tokens=600, system=_PHRASE_SYSTEM,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text").strip()
        return text or ans.answer
    except Exception:
        return ans.answer
