"""
reasoning/agent.py
───────────────────
Layer 8 — the agent core. A raw Anthropic-SDK tool-use loop: the model chooses
which READ tools to call, we execute them deterministically, and every number in
the final answer must trace to evidence a tool actually returned.

The honesty guarantees stay STRUCTURAL, not prompted:
  • The model never touches the DB — it can only call the Layer-7 read tools.
  • Tool results carry Evidence; the final answer is grounded against that
    evidence (the numeric guard), so a figure the model didn't get from a tool
    downgrades the answer's confidence.
  • Read tools execute inline; anything else only ever proposes (Layer 9).

Fallback: with no ANTHROPIC_API_KEY the deterministic keyword engine answers, so
the product works with or without a model. The agent is opt-in via AGENT_MODE=1
(or by calling run_agent directly) so it can be shadow-run before it replaces the
keyword path.
"""
from __future__ import annotations

import json
import logging
import os

from vinayak.reasoning.engine import Answer, Evidence, _num_tokens, _norm_num
from vinayak.memory import store as M
from vinayak.tools import registry
from vinayak.tools.executor import ToolContext, execute
from vinayak.tools.read_tools import register_all

logger = logging.getLogger(__name__)

MAX_ITERS = 5
MAX_TOOL_PAYLOAD = 6000   # chars of a tool result handed back to the model

# Sent as a follow-up when the model's answer contains a rupee figure that no
# tool returned. It gets ONE chance to rewrite using only the real figures
# before we fall back to a safe, evidence-only summary (the numeric guard).
_CORRECTION = (
    "STOP — one or more rupee figures in that answer were NOT in the tool "
    "results. Rewrite your answer now using ONLY the exact amounts the tools "
    "returned (copy them verbatim, e.g. '₹21.00 L'). Do not state, add, "
    "combine, or estimate any other number. If a figure you need isn't in the "
    "tool results, say plainly that it isn't available. Reply with the "
    "corrected answer only — do not call any more tools."
)

_AGENT_SYSTEM = (
    "You are the analyst layer of a business cockpit for an Indian SMB owner. "
    "Answer the owner's question using ONLY the tools provided — you have no other "
    "access to their data. Call the tools you need, then answer in clear, concise "
    "business English.\n"
    "RULES:\n"
    "• State a rupee figure or percentage ONLY if a tool returned it, and write it "
    "EXACTLY as the tool's evidence shows it (e.g. '₹21.00 L'). Never invent or "
    "recompute a number.\n"
    "• If the tools don't contain what's needed, say so plainly and name what's "
    "missing — do not guess.\n"
    "• Be direct: lead with the answer, then the one or two figures that support it."
)


def agent_available() -> bool:
    """True when a model is configured — the agent needs one to drive tool-use."""
    from vinayak.reasoning import llm
    return llm.is_active()


def enabled() -> bool:
    """Whether the agent path is switched on (shadow flag)."""
    return os.getenv("AGENT_MODE", "").strip().lower() in ("1", "true", "yes")


def should_use() -> bool:
    """True when the tool-calling agent should be the answer path. Default:
    use it whenever a model is configured; opt OUT with AGENT_MODE=0/off/false
    (then the deterministic keyword engine answers). The engine remains the
    automatic fallback inside run_agent if the model call ever fails."""
    if os.getenv("AGENT_MODE", "").strip().lower() in ("0", "off", "false", "no"):
        return False
    return agent_available()


def _grounded(text: str, evidence: list[Evidence]) -> bool:
    """Every money figure in `text` must trace to a tool's evidence — either its
    rounded display ('₹2.40 Cr') or its exact raw value ('₹2,39,53,022.37'). Both
    are legitimate ways to quote the same tool figure, so both are allowed;
    anything else fails closed and the numeric guard blocks it."""
    allowed: set[str] = set()
    for e in evidence:
        allowed |= _num_tokens(e.display)
        allowed |= _num_tokens(str(e.value))
        # The raw numeric value, normalised the way a ₹-prefixed quote of it would
        # be — so the model quoting the exact figure grounds cleanly.
        if isinstance(e.value, (int, float)) and not isinstance(e.value, bool):
            allowed.add(_norm_num(str(e.value)))
    return all(tok in allowed for tok in _num_tokens(text or ""))


def _confidence(grounded: bool, evidence: list[Evidence], used_tools: list[str],
                blocked: bool = False) -> str:
    if not used_tools:
        return "UNCERTAIN"          # answered without consulting any tool
    if blocked:
        return "PROBABLE"           # model tried to invent a figure; we fell back
    if grounded and evidence:
        return "CERTAIN"
    return "PROBABLE"               # tools used but a figure didn't verify cleanly


def _answer_text(resp) -> str:
    """Concatenate the text blocks of a model response."""
    return "".join(getattr(b, "text", "") for b in getattr(resp, "content", [])
                   if getattr(b, "type", None) == "text").strip()


def _safe_summary(evidence: list[Evidence]) -> str:
    """A grounded fallback that never surfaces a figure the tools didn't return.
    Used when the model keeps stating an uncited rupee amount even after a
    correction — we answer only from the evidence we actually hold."""
    if not evidence:
        return ("I couldn't find the figures needed to answer that reliably. "
                "Try asking about a specific metric (revenue, outstanding, overdue).")
    seen, parts = set(), []
    for e in evidence:
        if e.display in seen:
            continue
        seen.add(e.display)
        parts.append(f"{e.label}: {e.display}")
        if len(parts) >= 6:
            break
    return "Here's what the data shows — " + "; ".join(parts) + "."


def _system_prompt(conn, company_id: str) -> str:
    profile = {}
    try:
        profile = M.get_profile(conn, company_id) or {}
    except Exception:  # noqa: BLE001 — profile is best-effort context
        profile = {}
    bits = []
    for k in ("industry", "sub_vertical", "fiscal_year_start", "healthy_margin_pct", "seasonality"):
        if profile.get(k):
            bits.append(f"{k}: {profile[k]}")
    ctx = ("\nBusiness context — " + "; ".join(bits)) if bits else ""

    # Durable, owner-confirmed facts (payment terms, credit notes, …) — the same
    # memory the deterministic engine reasons with. Best-effort; never fatal.
    # These are CONTEXT, not evidence: the model may use them to reason, but any
    # rupee figure it states must still come from a tool result.
    try:
        facts = M.active_facts(conn, company_id)[:8]
        lines = [
            f"{f['entity_ref']} {f['claim_key']} = {f['claim_value']}"
            + (" (STALE — verify)" if f.get("status") == "stale" else "")
            for f in facts
        ]
        if lines:
            ctx += ("\nOwner-confirmed facts (context, not figures to quote): "
                    + "; ".join(lines))
    except Exception:  # noqa: BLE001 — facts are best-effort context
        pass
    return _AGENT_SYSTEM + ctx


def _finalize(question: str, text: str, evidence: list[Evidence], used_tools: list[str],
              note: str | None = None, blocked: bool = False) -> dict:
    grounded = _grounded(text, evidence)
    conf = _confidence(grounded, evidence, used_tools, blocked=blocked)
    if note:
        text = (text + f"\n\n{note}").strip()
    ans = Answer(
        question=question, intent="agent", answer=text, confidence=conf,
        evidence=list(evidence), data_used=list(dict.fromkeys(used_tools)),
        gates={"grounded": grounded, "tools_used": list(dict.fromkeys(used_tools)),
               "routed_by": "agent"},
    )
    out = ans.to_dict()
    out["meta"] = {
        "routed_by": "agent",
        "ai_active": True,
        "numeric_guard": "blocked" if blocked else "ok",
        "grounded": grounded,
    }
    return out


def run_agent(conn, company_id: str, question: str,
              history_turns: list[dict] | None = None,
              client=None, max_iters: int = MAX_ITERS) -> dict:
    """Answer a question by letting the model call read tools, grounded and gated.
    Falls back to the deterministic engine when no model is configured."""
    from vinayak.reasoning import llm, engine

    if client is None and not llm.is_active():
        # No model → keyword engine (already grounded + gated).
        return engine.answer(conn, company_id, question, use_llm=False,
                             history_turns=history_turns)

    client = client or llm._get_client()
    register_all()  # idempotent
    schemas = registry.anthropic_schemas(read_only=True)
    ctx = ToolContext(conn=conn, company_id=company_id)

    messages: list[dict] = []
    for t in (history_turns or [])[-4:]:
        if t.get("question"):
            messages.append({"role": "user", "content": t["question"]})
            messages.append({"role": "assistant", "content": t.get("answer", "")[:1500] or "…"})
    messages.append({"role": "user", "content": question})

    evidence_all: list[Evidence] = []
    used_tools: list[str] = []

    for _ in range(max_iters):
        try:
            resp = client.messages.create(
                model=llm.model_smart(), max_tokens=1024,
                system=_system_prompt(conn, company_id),
                tools=schemas, messages=messages,
            )
        except Exception as exc:  # noqa: BLE001 — a model/network failure falls back
            logger.warning("agent: model call failed (%s) — falling back to engine", exc)
            return engine.answer(conn, company_id, question, use_llm=False,
                                 history_turns=history_turns)

        messages.append({"role": "assistant", "content": resp.content})

        if getattr(resp, "stop_reason", None) != "tool_use":
            text = _answer_text(resp)
            # The numeric guard: if the model stated a rupee figure no tool
            # returned, give it ONE self-correcting retry, then fall back to a
            # safe evidence-only summary — never surface the invented number.
            if evidence_all and text and not _grounded(text, evidence_all):
                messages.append({"role": "user", "content": _CORRECTION})
                try:
                    fix = client.messages.create(
                        model=llm.model_smart(), max_tokens=1024,
                        system=_system_prompt(conn, company_id),
                        messages=messages,   # no tools: force a text rewrite
                    )
                    fixed = _answer_text(fix)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("agent: correction call failed (%s)", exc)
                    fixed = ""
                if fixed and _grounded(fixed, evidence_all):
                    return _finalize(question, fixed, evidence_all, used_tools)
                # Still ungrounded → block the invented figure, answer safely.
                return _finalize(question, _safe_summary(evidence_all),
                                 evidence_all, used_tools, blocked=True)
            return _finalize(question, text, evidence_all, used_tools)

        # Execute every tool the model asked for, hand results back.
        tool_results = []
        for block in resp.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            tool = registry.get(block.name)
            if tool is None or not tool.is_read:
                tool_results.append({"type": "tool_result", "tool_use_id": block.id,
                                     "content": "Tool not available.", "is_error": True})
                continue
            result = execute(ctx, tool, dict(block.input or {}))
            used_tools.append(tool.name)
            evidence_all.extend(result.evidence)
            content = (f"Error: {result.error}" if result.error
                       else json.dumps(result.data, default=str)[:MAX_TOOL_PAYLOAD])
            tool_results.append({"type": "tool_result", "tool_use_id": block.id,
                                 "content": content, "is_error": bool(result.error)})
        messages.append({"role": "user", "content": tool_results})

    # Loop budget exhausted — answer from what we gathered, flagged.
    return _finalize(question,
                     "I gathered some data but couldn't fully resolve that. Try a narrower question.",
                     evidence_all, used_tools, note=None)
