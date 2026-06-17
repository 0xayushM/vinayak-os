"""
reasoning/engine.py
────────────────────
Layer 3 — the AI reasoning pipeline. The design makes "say no" STRUCTURAL, not a
prompt suggestion:

    retrieve (deterministic)  →  reason  →  validate (deterministic)

  • retrieve: answer by calling the pre-aggregated queries.py functions + load
    the business profile and memory facts. Each number becomes a tagged piece of
    EVIDENCE with a stable id.
  • reason: build claims, each tagged computed | inference | unknown. A `computed`
    claim MUST cite an evidence id. An `unknown` becomes a question (routed to the
    memory capture loop). Phrasing may be done by Claude, but Claude is given ONLY
    the evidence — it can never introduce a number that wasn't retrieved.
  • validate: before returning, every `computed` claim is checked to trace to a
    real evidence id; if it doesn't, it is blocked/downgraded.

Three gates run around this: Data (is the data present/fresh?), Rule (do we know
how to answer this?), Confidence (CERTAIN / PROBABLE / UNCERTAIN).

Today the reasoner is fully deterministic (no LLM key required). If
ANTHROPIC_API_KEY is set, `llm_phrase()` rewrites the final prose from the
*validated* claims only — numbers stay deterministic either way.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

# ── Numeric guard — the LLM may not surface a MONEY figure we didn't compute ──
# Rupee amounts are the high-stakes numbers that must be exact, so every money
# token (₹… or a number with a lakh/crore/k suffix) must trace to a figure we
# actually produced. Percentages are analytical (and the prompt forbids inventing
# them) so we don't hard-block on those; counts/dates are fine too.
_MONEY_RE = re.compile(
    r"₹\s?\d[\d.,]*\s?(?:cr|crore|crores|lakh|lakhs|l|k)?"
    r"|\b\d[\d.,]*\s?(?:cr|crore|crores|lakh|lakhs|l|k)\b",
    re.IGNORECASE,
)


def _norm_num(tok: str) -> str:
    t = tok.lower().replace("₹", "").replace(",", "").replace(" ", "")
    t = (t.replace("crores", "cr").replace("crore", "cr")
          .replace("lakhs", "l").replace("lakh", "l"))
    return t


def _num_tokens(s: str) -> set[str]:
    return {_norm_num(m.group(0)) for m in _MONEY_RE.finditer(s or "")}


def _numbers_supported(text: str, ans: "Answer") -> bool:
    """True iff every money/percent figure in `text` traces to a number we
    actually computed (claims, evidence, the deterministic answer)."""
    corpus = " ".join(
        [ans.answer] + [c.text for c in ans.claims]
        + [e.display for e in ans.evidence] + ans.assumptions + ans.what_i_dont_know
    )
    allowed = _num_tokens(corpus)
    return all(tok in allowed for tok in _num_tokens(text))

from vinayak.schema import queries as Q
from vinayak.memory import store as M


# ── value formatting (Indian) ─────────────────────────────────────────────────
def inr(n: float | int | None) -> str:
    if n is None:
        return "—"
    n = float(n)
    if abs(n) >= 1e7:
        return f"₹{n/1e7:.2f}Cr"
    if abs(n) >= 1e5:
        return f"₹{n/1e5:.2f}L"
    if abs(n) >= 1e3:
        return f"₹{n/1e3:.1f}K"
    return f"₹{n:.0f}"


def _win(period) -> dict:
    """Date-range kwargs for the query functions, or empty for default window."""
    return {"start": period["start"], "end": period["end"]} if period else {}


def _when(period, default="recently") -> str:
    return period["label"] if period else default


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


# ── data shapes ───────────────────────────────────────────────────────────────
@dataclass
class Evidence:
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


# ── intent routing (rule-based; LLM can refine later) ─────────────────────────
INTENTS: list[tuple[str, list[str]]] = [
    # Wave 1 analytical intents (specific phrasings first so they win).
    ("business_pulse",  ["briefing", "brief me", "morning brief", "business pulse", "how is my business",
                          "how are we doing", "business health", "catch me up", "overall summary", "give me an overview"]),
    ("collections_priority", ["who should i chase", "who to chase", "chase up", "chase payment",
                              "chase customers", "collect from", "follow up on payment",
                              "collections priority", "prioritise collection", "prioritize collection"]),
    ("dso",             ["dso", "days sales outstanding", "get paid", "getting paid", "how fast am i paid",
                          "collection period", "days to collect", "to collect payment", "how long to collect"]),
    ("customer_movement", ["new customer", "new customers", "lost customer", "stopped buying", "lapsed",
                            "slipping away", "at risk customer", "churn", "haven't bought", "gone quiet"]),
    ("customer_changes", ["which customers grew", "customers grew", "customers shrank", "buying more", "buying less",
                           "grew or shrank", "customer growth", "who grew", "who declined", "ordering less"]),
    ("reorder_alert",   ["run out", "running out", "running low", "reorder", "restock", "low on stock",
                          "about to finish", "stockout", "days of cover", "need to order"]),
    ("inventory_turnover", ["turnover", "stock turns", "how fast is my stock", "inventory days", "dio",
                             "how fast does stock move", "stock velocity"]),
    ("sales_by_category", ["by category", "which category", "category wise", "product category",
                            "categories sell", "sales by category", "category breakdown"]),
    ("least_skus",      ["least selling", "least-selling", "least sold", "worst selling", "worst-selling",
                          "lowest selling", "lowest-selling", "slowest selling", "weakest selling",
                          "least popular", "bottom selling", "bottom-selling", "worst performing product",
                          "underperforming product", "least revenue", "lowest revenue product",
                          "lowest selling", "selling the least", "sell the least", "sells the least"]),

    ("payment_stretch", ["stretch", "terms", "paying late", "slow pay", "beyond terms"]),
    ("receivables",     ["owe", "owes", "outstanding", "receivable", "collect", "overdue payment", "ar "]),
    ("concentration",   ["depend", "concentration", "too reliant", "risk", "most of my sales", "biggest customer"]),
    ("top_customers",   ["top customer", "best customer", "biggest customers", "who buys"]),
    ("revenue_trend",   ["trend", "over the last", "month over month", "mom", "growing", "declining",
                          "decline", "declined", "drop", "dropped", "fell", "fall", "falling",
                          "lower than", "down from", "which month", "best month", "worst month",
                          "compare month", "month by month", "growth", "grew", "6 month", "monthly"]),
    ("margin",          ["margin", "profit", "profitability", "markup"]),
    ("forecast",        ["forecast", "next quarter", "next month", "predict", "will i", "future"]),
    ("overdue_orders",  ["sales order", "order late", "late to deliver", "overdue order", "delivery late"]),
    ("overdue_pos",     ["purchase order", "po ", "pos ", "supplier late", "vendor late"]),
    ("top_skus",        ["product", "sku", "item sells", "best selling", "most money"]),
    ("revenue",         ["revenue", "sales", "sold", "did i sell", "how much did i sell", "turnover", "billed"]),
    ("dead_stock",      ["dead stock", "dead-stock", "sitting", "not moving", "slow moving", "obsolete"]),
    ("purchases",       ["purchase", "spend", "buying", "vendor", "supplier"]),
    ("inventory",       ["stock value", "inventory", "how much stock"]),
    ("creditworthy",    ["trustworthy", "safe to extend", "give credit", "creditworthy", "reliable customer"]),
]


def classify(question: str) -> str:
    q = question.lower()
    for intent, kws in INTENTS:
        if any(k in q for k in kws):
            return intent
    return "unknown"


def _entity_in(question: str, conn, company_id: str) -> str | None:
    """Best-effort: match a customer name mentioned in the question."""
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT customer_name FROM canon_ar_flat WHERE company_id=%s", (company_id,))
        names = [r[0] for r in cur.fetchall() if r[0]]
    ql = question.lower()
    for n in names:
        # match on the first distinctive word of the customer name
        first = re.split(r"\s+", n.strip())[0].lower()
        if len(first) >= 3 and first in ql:
            return n
    return None


# ── handlers ──────────────────────────────────────────────────────────────────
# Each returns (answer_text, confidence, claims, evidence, extras)
def _h_concentration(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_customer_concentration(conn, cid, **_win(period))
    slices = [s for s in d.get("slices", []) if s["name"] != "Others"]
    total = d.get("total", 0)
    when = _when(period, "lately")
    if not slices or total <= 0:
        return _no_data(q, "concentration", f"I don't see any sales {when}, so I can't judge customer concentration.")
    ev, claims = [], []
    top = slices[0]
    top_pct = 100 * top["value"] / total if total else 0
    top3 = sum(s["value"] for s in slices[:3])
    top3_pct = 100 * top3 / total if total else 0
    ev.append(Evidence("conc_total", "Total sales in window", total, inr(total)))
    ev.append(Evidence("conc_top", f"Top customer ({top['name']})", top["value"], f"{inr(top['value'])} ({top_pct:.0f}%)"))
    ev.append(Evidence("conc_top3", "Top 3 customers share", top3_pct, f"{top3_pct:.0f}% of sales"))
    claims.append(Claim(f"{top['name']} alone is {top_pct:.0f}% of your sales {when}.", "computed", ["conc_top"]))
    claims.append(Claim(f"Your top 3 customers together are {top3_pct:.0f}% of sales.", "computed", ["conc_top3"]))
    conf = "CERTAIN"
    if top3_pct >= 50:
        claims.append(Claim("Losing any one of them would hit revenue hard — that's a real concentration risk.", "inference",
                            assumption="treating more than half of sales from the top 3 as a concentration risk"))
        conf = "PROBABLE"
        ans = (f"Yes — you're fairly dependent on a few accounts. {top['name']} is {top_pct:.0f}% of your sales "
               f"{when}, and your top 3 customers make up {top3_pct:.0f}%. Losing one would hurt.")
    else:
        ans = (f"Not heavily. {when.capitalize() if when[0].islower() else when}, your biggest customer "
               f"{top['name']} is {top_pct:.0f}% of sales and the top 3 are {top3_pct:.0f}% — reasonably spread.")
    chart = {"title": f"Share of sales {when}", "unit": "₹",
             "items": [{"name": s["name"], "value": s["value"], "display": inr(s["value"])} for s in slices[:6]]}
    return Answer(q, "concentration", ans, conf, claims, ev,
                  assumptions=([c.assumption for c in claims if c.assumption]),
                  data_used=["customer_concentration"], chart=chart)


def _h_top_customers(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_top_customers_revenue(conn, cid, **_win(period))
    custs = d.get("customers", [])[:5]
    when = _when(period, "lately")
    if not custs:
        return _no_data(q, "top_customers", f"I don't see any customer sales {when}.")
    ev = []
    for i, c in enumerate(custs):
        ev.append(Evidence(f"cust_{i}", c["customer_name"], c["revenue"], f"{inr(c['revenue'])} ({c['pct_of_total']:.0f}%)"))
    shown_total = sum(c["revenue"] for c in custs)
    ev.append(Evidence("tc_total", "Top-5 total", shown_total, inr(shown_total)))
    listing = ", ".join(f"{c['customer_name']} ({inr(c['revenue'])})" for c in custs[:3])
    claims = [Claim(f"Top customers {when}: " + "; ".join(f"{c['customer_name']} {inr(c['revenue'])}" for c in custs) + ".",
                    "computed", [e.id for e in ev]),
              Claim(f"Those top {len(custs)} customers total {inr(shown_total)}.", "computed", ["tc_total"])]
    chart = {"title": f"Top customers {when}", "unit": "₹",
             "items": [{"name": c["customer_name"], "value": c["revenue"], "display": inr(c["revenue"])} for c in custs]}
    return Answer(q, "top_customers", f"Your biggest customers {when} are {listing}.",
                  "CERTAIN", claims, ev, data_used=["top_customers_revenue"], chart=chart)


def _h_revenue(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_revenue_summary(conn, cid, **_win(period))
    goods, inv, n = d.get("period_total_goods", 0), d.get("period_total_invoiced", 0), d.get("invoice_count", 0)
    when = _when(period, "in the latest period")
    if n == 0:
        return _no_data(q, "revenue", f"I don't see any invoices {when}.")
    ev = [Evidence("rev_inv", "Sales (invoice total, incl. tax)", inv, inr(inv)),
          Evidence("rev_goods", "Sales before tax", goods, inr(goods)),
          Evidence("rev_n", "Invoices", n, str(n))]
    claims = [Claim(f"Sales {when} were {inr(inv)} across {n} invoices ({inr(goods)} before tax).",
                    "computed", ["rev_inv", "rev_goods", "rev_n"])]
    return Answer(q, "revenue", f"{_cap(when)}, you billed {inr(inv)} across {n} invoices ({inr(goods)} before tax).",
                  "CERTAIN", claims, ev, data_used=["revenue_summary"])


def _mon(ym: str) -> str:
    """'2026-06' -> 'Jun 2026'."""
    try:
        y, m = ym.split("-")
        import calendar
        return f"{calendar.month_abbr[int(m)]} {y}"
    except Exception:
        return ym


def _h_revenue_trend(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_revenue_trend(conn, cid, months=6)
    months = [m for m in d.get("months", []) if m["revenue"] > 0]
    if len(months) < 2:
        return _no_data(q, "revenue_trend", "There isn't enough monthly history yet to compare months.")

    # Per-month evidence + month-over-month change, so we can point at the
    # specific months that fell vs the one before.
    ev, declines, rises = [], [], []
    for i, m in enumerate(months):
        ev.append(Evidence(f"mo_{i}", _mon(m["month"]), m["revenue"], inr(m["revenue"])))
        if i > 0 and months[i - 1]["revenue"]:
            chg = 100 * (m["revenue"] - months[i - 1]["revenue"]) / months[i - 1]["revenue"]
            (declines if chg < 0 else rises).append((m, months[i - 1], chg))

    series_claim = Claim(
        "Monthly sales: " + "; ".join(f"{_mon(m['month'])} {inr(m['revenue'])}" for m in months) + ".",
        "computed", [e.id for e in ev])
    claims = [series_claim]

    if declines:
        detail = "; ".join(f"{_mon(m['month'])} fell {abs(chg):.0f}% from {_mon(p['month'])}"
                           for (m, p, chg) in declines)
        claims.append(Claim(f"Months where sales dropped vs the month before: {detail}.", "computed", [e.id for e in ev]))
        names = ", ".join(_mon(m["month"]) for (m, _, _) in declines)
        ans = f"Sales fell month-on-month in {len(declines)} month(s): {names}."
    else:
        ans = "Sales held up or grew every month in the window — no month-over-month decline."

    last, prev = months[-1], months[-2]
    lastchg = 100 * (last["revenue"] - prev["revenue"]) / prev["revenue"] if prev["revenue"] else 0
    claims.append(Claim(
        f"Most recent: {_mon(last['month'])} was {inr(last['revenue'])}, "
        f"{'up' if lastchg >= 0 else 'down'} {abs(lastchg):.0f}% from {_mon(prev['month'])}.",
        "computed", [f"mo_{len(months)-1}", f"mo_{len(months)-2}"]))

    chart = {"title": "Monthly sales", "unit": "₹",
             "items": [{"name": _mon(m["month"]), "value": m["revenue"], "display": inr(m["revenue"])} for m in months]}
    return Answer(q, "revenue_trend", ans, "CERTAIN", claims, ev,
                  data_used=["revenue_trend"], chart=chart)


def _h_receivables(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_ar_summary(conn, cid)
    total, overdue = d.get("total_outstanding", 0), d.get("overdue_value", 0)
    if total <= 0:
        return _no_data(q, "receivables", "No outstanding receivables on record.")
    exp = d.get("top_exposures", [])[:5]
    ev = [Evidence("ar_total", "Total outstanding", total, inr(total)),
          Evidence("ar_overdue", "Overdue", overdue, inr(overdue))]
    pct = 100 * overdue / total if total else 0
    claims = [Claim(f"Customers owe you {inr(total)} in total, and {inr(overdue)} of that is overdue.", "computed", ["ar_total", "ar_overdue"])]
    names = []
    for i, e in enumerate(exp):
        ev.append(Evidence(f"exp_{i}", e["customer_name"], e["outstanding"], f"{inr(e['outstanding'])} ({e['oldest_days']}d oldest)"))
        names.append(f"{e['customer_name']} ({inr(e['outstanding'])})")
    if names:
        claims.append(Claim("The biggest amounts are owed by " + ", ".join(names) + ".", "computed", [f"exp_{i}" for i in range(len(exp))]))
    ans = (f"You're owed {inr(total)} in total — {inr(overdue)} of it ({pct:.0f}%) is overdue. "
           f"The largest is {names[0]}." if names else f"You're owed {inr(total)} ({inr(overdue)} overdue).")
    chart = {"title": "Largest amounts owed", "unit": "₹",
             "items": [{"name": e["customer_name"], "value": e["outstanding"], "display": inr(e["outstanding"])} for e in exp]}
    return Answer(q, "receivables", ans, "CERTAIN", claims, ev, data_used=["ar_summary"], chart=chart)


def _h_payment_stretch(conn, cid, q, entity, period=None) -> Answer:
    """The memory showcase: combine AR aging with the owner's known terms facts."""
    exposures = Q.get_ar_customer_exposure(conn, cid).get("customers", [])
    facts = {f["entity_ref"].split(":", 1)[-1].lower(): f
             for f in M.active_facts(conn, cid) if f["claim_key"] == "payment_terms_days"}
    if not exposures:
        return _no_data(q, "payment_stretch", "No receivables to assess.")
    ev, claims, flagged, unknown_terms = [], [], [], []
    for i, c in enumerate(exposures[:8]):
        oldest = c.get("oldest_days", 0)
        name = c["customer_name"]
        fact = facts.get(name.lower())
        if fact is None:
            unknown_terms.append(name)
            continue
        terms = int(fact["claim_value"])
        eid = f"str_{i}"
        ev.append(Evidence(eid, f"{name}: oldest open invoice", oldest, f"{oldest}d vs {terms}d terms"))
        if oldest > terms:
            stale_note = " (and you told me these terms a while ago — worth reconfirming)" if fact["status"] == "stale" else ""
            claims.append(Claim(f"{name} has invoices {oldest}d old vs their {terms}-day terms — stretching by {oldest-terms}d{stale_note}.",
                                "inference", [eid], assumption=f"using your saved {terms}-day terms for {name}"))
            flagged.append(name)
    # Decide confidence + questions
    what_dk, suggested = [], None
    if unknown_terms:
        what_dk.append("I don't know the agreed payment terms for: " + ", ".join(unknown_terms[:5]) + ".")
        suggested = {"entity_type": "customer", "entity_ref": f"customer:{unknown_terms[0]}",
                     "claim_key": "payment_terms_days", "prompt": f"What are {unknown_terms[0]}'s payment terms (days)?"}
    if flagged:
        ans = "These customers are stretching beyond their terms: " + ", ".join(flagged) + "."
        conf = "PROBABLE"
    elif facts:
        ans = "Within the terms you've told me, no customer is materially stretching right now."
        conf = "PROBABLE"
    else:
        ans = "I can't judge this yet — I don't have payment terms saved for your customers."
        conf = "UNCERTAIN"
    return Answer(q, "payment_stretch", ans, conf, claims, ev,
                  assumptions=[c.assumption for c in claims if c.assumption],
                  data_used=["ar_customer_exposure", "memory:payment_terms_days"],
                  what_i_dont_know=what_dk, suggested_fact=suggested)


def _h_dead_stock(conn, cid, q, entity, period=None) -> Answer:
    since = 90
    d = Q.get_dead_stock(conn, cid, since_days=since)
    items = d.get("items", [])[:6]
    dead_n, dead_val = d.get("dead_count", 0), d.get("dead_value", 0)
    if not items:
        return Answer(q, "dead_stock",
                      f"Good news — every item you hold has sold at least once in the last {since} days, "
                      "so nothing is obviously sitting idle.",
                      "PROBABLE", [Claim(f"No held SKU is without a sale in the last {since} days.", "computed")],
                      [], data_used=["dead_stock"])
    ev = [Evidence(f"ds_{i}", s["sku_name"] or s["sku_code"], s["total_value"], inr(s["total_value"]))
          for i, s in enumerate(items)]
    ev.append(Evidence("ds_total", "Capital in non-moving stock", dead_val, inr(dead_val)))
    claims = [
        Claim(f"{dead_n} items you hold (worth {inr(dead_val)}) have NOT sold in the last {since} days.",
              "computed", ["ds_total"]),
        Claim("The biggest by value tied up: " + "; ".join(f"{s['sku_name'] or s['sku_code']} {inr(s['total_value'])}" for s in items) + ".",
              "computed", [f"ds_{i}" for i in range(len(items))]),
        Claim("'Not sold recently' is the signal; this can include machinery, raw material or scrap that "
              "isn't meant for resale, so review the list before acting.", "inference",
              assumption="no sale in the window = not moving"),
    ]
    chart = {"title": "Value tied up in non-moving stock", "unit": "₹",
             "items": [{"name": s["sku_name"] or s["sku_code"], "value": s["total_value"], "display": inr(s["total_value"])} for s in items]}
    return Answer(q, "dead_stock",
                  f"{dead_n} items worth {inr(dead_val)} haven't sold in the last {since} days — that's capital sitting idle.",
                  "PROBABLE", claims, ev,
                  assumptions=["no sale in the last 90 days = not moving"],
                  data_used=["dead_stock"],
                  what_i_dont_know=["whether a flagged item is a non-resale item (machinery, raw material, scrap)"],
                  chart=chart)


def _h_top_skus(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_top_skus_revenue(conn, cid, **_win(period))
    skus = d.get("skus", [])[:5]
    when = _when(period, "lately")
    if not skus:
        return _no_data(q, "top_skus", f"I don't see any product sales {when}.")
    ev = [Evidence(f"sk_{i}", s["sku_name"] or s["sku_code"], s["revenue"], inr(s["revenue"])) for i, s in enumerate(skus)]
    shown_total = sum(s["revenue"] for s in skus)
    ev.append(Evidence("sk_total", "Top SKUs total", shown_total, inr(shown_total)))
    listing = ", ".join(f"{(s['sku_name'] or s['sku_code'])} ({inr(s['revenue'])})" for s in skus[:3])
    claims = [Claim(f"Top products by revenue {when}: " + "; ".join(f"{s['sku_name'] or s['sku_code']} {inr(s['revenue'])}" for s in skus) + ".",
                    "computed", [e.id for e in ev]),
              Claim(f"Those top products total {inr(shown_total)}.", "computed", ["sk_total"])]
    chart = {"title": f"Top products {when}", "unit": "₹",
             "items": [{"name": s["sku_name"] or s["sku_code"], "value": s["revenue"], "display": inr(s["revenue"])} for s in skus]}
    return Answer(q, "top_skus", f"Your best-selling products {when} are {listing}.", "CERTAIN", claims, ev,
                  data_used=["top_skus_revenue"], chart=chart)


def _h_least_skus(conn, cid, q, entity, period=None) -> Answer:
    # "Till now" → whole-dataset window unless the user gave an explicit period.
    d = Q.get_bottom_skus_revenue(conn, cid, **_win(period))
    skus = d.get("skus", [])[:5]
    when = _when(period, "till now")
    if not skus:
        return _no_data(q, "least_skus", f"I don't see any product sales {when}.")
    ev = [Evidence(f"ls_{i}", s["sku_name"] or s["sku_code"], s["revenue"], inr(s["revenue"])) for i, s in enumerate(skus)]
    listing = ", ".join(f"{(s['sku_name'] or s['sku_code'])} ({inr(s['revenue'])})" for s in skus[:3])
    claims = [
        Claim("Lowest-revenue products that still sold " + when + ": "
              + "; ".join(f"{s['sku_name'] or s['sku_code']} {inr(s['revenue'])} "
                          f"({s['quantity']:.0f} units, {s['invoice_count']} invoices)" for s in skus) + ".",
              "computed", [e.id for e in ev]),
        Claim("These are your weakest sellers, not non-sellers — products you hold that have "
              "never sold show up under dead / non-moving stock, not here.",
              "inference", assumption="only SKUs with revenue > 0 in the window are included"),
    ]
    chart = {"title": f"Lowest-selling products {when}", "unit": "₹",
             "items": [{"name": s["sku_name"] or s["sku_code"], "value": s["revenue"], "display": inr(s["revenue"])} for s in skus]}
    return Answer(q, "least_skus",
                  f"Your lowest-selling products {when} are {listing} — these brought in the least revenue among items that sold.",
                  "CERTAIN", claims, ev,
                  data_used=["bottom_skus_revenue"], chart=chart)


def _h_purchases(conn, cid, q, entity, period=None) -> Answer:
    w = _win(period)
    d = Q.get_purchases_summary(conn, cid, **w)
    spend, nv = d.get("period_spend_goods", d.get("period_spend", 0)), d.get("vendor_count", 0)
    when = _when(period, "lately")
    if not spend:
        return _no_data(q, "purchases", f"I don't see any purchases {when}.")
    tv = Q.get_top_vendors_spend(conn, cid, **w).get("vendors", [])[:3]
    ev = [Evidence("pur_spend", "Purchase spend", spend, inr(spend)),
          Evidence("pur_vendors", "Active vendors", nv, str(nv))]
    for i, v in enumerate(tv):
        ev.append(Evidence(f"ven_{i}", v["vendor_name"], v["spend"], inr(v["spend"])))
    claims = [Claim(f"You spent {inr(spend)} on purchases {when} across {nv} vendors.", "computed", ["pur_spend", "pur_vendors"])]
    vtxt = ""
    if tv:
        claims.append(Claim("Most went to " + ", ".join(f"{v['vendor_name']} ({inr(v['spend'])})" for v in tv) + ".",
                            "computed", [f"ven_{i}" for i in range(len(tv))]))
        vtxt = f" Most of it went to {tv[0]['vendor_name']}."
    chart = ({"title": f"Top vendors by spend {when}", "unit": "₹",
              "items": [{"name": v["vendor_name"], "value": v["spend"], "display": inr(v["spend"])} for v in tv]} if tv else None)
    return Answer(q, "purchases", f"{_cap(when)}, you spent {inr(spend)} across {nv} vendors.{vtxt}", "CERTAIN", claims, ev,
                  data_used=["purchases_summary", "top_vendors_spend"], chart=chart)


def _h_inventory(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_inventory_summary(conn, cid)
    val, skus = d.get("total_value", 0), d.get("total_skus", 0)
    if not skus:
        return _no_data(q, "inventory", "No inventory on record.")
    ev = [Evidence("inv_val", "Stock value", val, inr(val)), Evidence("inv_skus", "SKUs tracked", skus, str(skus))]
    claims = [Claim(f"You hold {inr(val)} of stock across {skus} SKUs.", "computed", ["inv_val", "inv_skus"])]
    return Answer(q, "inventory", f"Stock value {inr(val)} across {skus} SKUs.", "CERTAIN", claims, ev, data_used=["inventory_summary"])


def _h_overdue_pos(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_overdue_pos(conn, cid)
    n, val = d.get("total_overdue_count", 0), d.get("total_value_at_risk", 0)
    ev = [Evidence("po_n", "Overdue POs", n, str(n)), Evidence("po_val", "Value at risk", val, inr(val))]
    claims = [Claim(f"{n} purchase orders are overdue, {inr(val)} of value at risk.", "computed", ["po_n", "po_val"])]
    return Answer(q, "overdue_pos", f"{n} overdue POs ({inr(val)} at risk).", "CERTAIN", claims, ev, data_used=["overdue_pos"])


def _h_overdue_orders(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_overdue_orders(conn, cid)
    n, val = d.get("total_overdue_count", 0), d.get("total_value", 0)
    ev = [Evidence("oo_n", "Overdue orders", n, str(n)), Evidence("oo_val", "Value", val, inr(val))]
    claims = [Claim(f"{n} sales orders are past their delivery date, worth {inr(val)}.", "computed", ["oo_n", "oo_val"])]
    return Answer(q, "overdue_orders", f"{n} overdue sales orders ({inr(val)}).", "CERTAIN", claims, ev, data_used=["overdue_orders"])


def _h_margin(conn, cid, q, entity, period=None) -> Answer:
    a = Answer(q, "margin", "I can't compute margin reliably — I have sales values but no cost-of-goods data yet.",
               "UNCERTAIN", [Claim("Margin needs cost-of-goods, which isn't in the synced data.", "unknown")],
               [], what_i_dont_know=["cost of goods / purchase cost per SKU"])
    a.suggested_fact = {"entity_type": "company", "entity_ref": "company:self", "claim_key": "avg_gross_margin_pct",
                        "prompt": "If you know your typical gross margin %, tell me and I'll use it."}
    return a


def _h_forecast(conn, cid, q, entity, period=None) -> Answer:
    return Answer(q, "forecast", "I can't forecast that reliably — I don't have your forward order book.",
                  "UNCERTAIN", [Claim("A forecast needs the forward order book / pipeline, which isn't synced.", "unknown")],
                  [], what_i_dont_know=["forward order book / confirmed future orders"])


def _h_creditworthy(conn, cid, q, entity, period=None) -> Answer:
    name = entity or "that customer"
    return Answer(q, "creditworthy",
                  f"That's a judgment call I shouldn't make alone — I can show {name}'s payment history, but trust is yours to set.",
                  "UNCERTAIN",
                  [Claim("Creditworthiness is a judgment, not a number in the data.", "unknown")],
                  [], what_i_dont_know=[f"your view of {name}'s reliability (tell me and I'll remember it)"],
                  suggested_fact={"entity_type": "customer", "entity_ref": f"customer:{name}",
                                  "claim_key": "relationship", "prompt": f"How would you rate {name} (trusted / watch / risky)?"})


# ── Wave 1 analytical handlers ────────────────────────────────────────────────
def _h_business_pulse(conn, cid, q, entity, period=None) -> Answer:
    rev = Q.get_revenue_summary(conn, cid)
    ar = Q.get_ar_summary(conn, cid)
    conc = Q.get_customer_concentration(conn, cid)
    dead = Q.get_dead_stock(conn, cid)
    slices = [s for s in conc.get("slices", []) if s["name"] != "Others"]
    total = conc.get("total", 0)
    top_pct = (100 * slices[0]["value"] / total) if (slices and total) else 0
    ev = [
        Evidence("p_sales", "Recent sales", rev.get("period_total_invoiced", 0), inr(rev.get("period_total_invoiced", 0))),
        Evidence("p_ar", "Outstanding", ar.get("total_outstanding", 0), inr(ar.get("total_outstanding", 0))),
        Evidence("p_overdue", "Overdue", ar.get("overdue_value", 0), inr(ar.get("overdue_value", 0))),
        Evidence("p_dead", "Idle stock", dead.get("dead_value", 0), inr(dead.get("dead_value", 0))),
    ]
    claims = [
        Claim(f"Recent sales: {inr(rev.get('period_total_invoiced',0))} across {rev.get('invoice_count',0)} invoices.", "computed", ["p_sales"]),
        Claim(f"You're owed {inr(ar.get('total_outstanding',0))}, of which {inr(ar.get('overdue_value',0))} is overdue.", "computed", ["p_ar", "p_overdue"]),
        Claim(f"Your top customer is {top_pct:.0f}% of sales.", "computed", ["p_sales"]),
        Claim(f"{dead.get('dead_count',0)} items ({inr(dead.get('dead_value',0))}) are idle stock.", "computed", ["p_dead"]),
    ]
    ans = (f"Snapshot — sales {inr(rev.get('period_total_invoiced',0))}; owed {inr(ar.get('total_outstanding',0))} "
           f"({inr(ar.get('overdue_value',0))} overdue); top customer {top_pct:.0f}% of sales; "
           f"{inr(dead.get('dead_value',0))} in idle stock.")
    return Answer(q, "business_pulse", ans, "CERTAIN", claims, ev,
                  data_used=["revenue_summary", "ar_summary", "customer_concentration", "dead_stock"])


def _h_collections(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_collections_priority(conn, cid)
    items = d.get("items", [])[:5]
    if not items:
        return Answer(q, "collections_priority", "Nothing is overdue right now — no collections to prioritise.",
                      "CERTAIN", [Claim("No overdue receivables.", "computed")], [], data_used=["collections_priority"])
    ev = [Evidence("co_total", "Total overdue", d["total_overdue"], inr(d["total_overdue"]))]
    for i, c in enumerate(items):
        ev.append(Evidence(f"co_{i}", c["customer_name"], c["outstanding"], f"{inr(c['outstanding'])} ({c['days_overdue']}d)"))
    claims = [
        Claim(f"{inr(d['total_overdue'])} is overdue in total.", "computed", ["co_total"]),
        Claim("Chase in this order (biggest impact first): " + "; ".join(
            f"{c['customer_name']} {inr(c['outstanding'])} ({c['days_overdue']}d late)" for c in items) + ".",
            "computed", [f"co_{i}" for i in range(len(items))]),
    ]
    chart = {"title": "Overdue by customer", "unit": "₹",
             "items": [{"name": c["customer_name"], "value": c["outstanding"], "display": inr(c["outstanding"])} for c in items]}
    return Answer(q, "collections_priority",
                  f"Start with {items[0]['customer_name']} — {inr(items[0]['outstanding'])} and {items[0]['days_overdue']} days late.",
                  "CERTAIN", claims, ev, data_used=["collections_priority"], chart=chart)


def _h_dso(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_dso(conn, cid)
    if d["dso_days"] is None:
        return _no_data(q, "dso", "I can't compute collection days without recent sales.")
    ev = [Evidence("dso_v", "Days Sales Outstanding", d["dso_days"], f"{d['dso_days']} days"),
          Evidence("dso_ar", "Outstanding", d["outstanding"], inr(d["outstanding"]))]
    claims = [Claim(f"On average it's taking about {d['dso_days']} days to collect, against {inr(d['outstanding'])} outstanding.",
                    "computed", ["dso_v", "dso_ar"]),
              Claim("Distributors typically target 30–60 days; well above that ties up cash.", "inference",
                    assumption="using a common distribution benchmark of 30-60 days")]
    return Answer(q, "dso", f"You're collecting in roughly {d['dso_days']} days on average.",
                  "PROBABLE", claims, ev, assumptions=["DSO is an average over the trailing window"], data_used=["dso"])


def _h_customer_changes(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_customer_changes(conn, cid)
    up, down = d.get("up", []), d.get("down", [])
    if not up and not down:
        return _no_data(q, "customer_changes", "I don't have two comparable periods of sales yet.")
    ev, claims = [], []
    for i, m in enumerate(up):
        ev.append(Evidence(f"up_{i}", m["customer_name"], m["delta"], f"+{inr(m['delta'])}"))
    for i, m in enumerate(down):
        ev.append(Evidence(f"dn_{i}", m["customer_name"], m["delta"], f"-{inr(abs(m['delta']))}"))
    if up:
        claims.append(Claim("Growing: " + "; ".join(f"{m['customer_name']} +{inr(m['delta'])}" for m in up) + ".",
                            "computed", [f"up_{i}" for i in range(len(up))]))
    if down:
        claims.append(Claim("Shrinking: " + "; ".join(f"{m['customer_name']} -{inr(abs(m['delta']))}" for m in down) + ".",
                            "computed", [f"dn_{i}" for i in range(len(down))]))
    ans = ""
    if down:
        ans += f"Watch {down[0]['customer_name']} — down {inr(abs(down[0]['delta']))} vs the prior period. "
    if up:
        ans += f"{up[0]['customer_name']} grew the most (+{inr(up[0]['delta'])})."
    return Answer(q, "customer_changes", ans or "Customer revenue was broadly stable.",
                  "CERTAIN", claims, ev, data_used=["customer_changes"])


def _h_customer_movement(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_customer_movement(conn, cid)
    new, lapsed = d.get("new", []), d.get("lapsed", [])
    ev, claims = [], []
    for i, c in enumerate(new):
        ev.append(Evidence(f"nw_{i}", c["customer_name"], c["lifetime"], inr(c["lifetime"])))
    for i, c in enumerate(lapsed):
        ev.append(Evidence(f"lp_{i}", c["customer_name"], c["lifetime"], f"{inr(c['lifetime'])}, {c['days_since']}d ago"))
    if lapsed:
        claims.append(Claim("Customers who used to buy but have gone quiet: " + "; ".join(
            f"{c['customer_name']} (last {c['days_since']}d ago, {inr(c['lifetime'])} lifetime)" for c in lapsed) + ".",
            "computed", [f"lp_{i}" for i in range(len(lapsed))]))
    if new:
        claims.append(Claim("Newly acquired customers: " + ", ".join(c["customer_name"] for c in new) + ".",
                            "computed", [f"nw_{i}" for i in range(len(new))]))
    if not new and not lapsed:
        return _no_data(q, "customer_movement", "No notable new or lapsed customers in the window.")
    ans = ""
    if lapsed:
        ans += f"{len(lapsed)} customer(s) have stopped buying recently — biggest is {lapsed[0]['customer_name']}. "
    if new:
        ans += f"{len(new)} new customer(s) came on board."
    return Answer(q, "customer_movement", ans.strip(), "CERTAIN", claims, ev,
                  data_used=["customer_movement"],
                  what_i_dont_know=([] if lapsed else ["whether quiet customers churned or are just between orders"]))


def _h_reorder(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_reorder_alert(conn, cid)
    items = d.get("items", [])[:6]
    if not items:
        return Answer(q, "reorder_alert", "Nothing looks close to running out based on recent sales pace.",
                      "PROBABLE", [Claim("No fast-moving item is below its cover threshold.", "computed")], [],
                      data_used=["reorder_alert"])
    ev = [Evidence(f"ro_{i}", s["sku_name"] or s["sku_code"], s["days_of_cover"], f"{s['days_of_cover']}d cover")
          for i, s in enumerate(items)]
    claims = [Claim("Running low (days of stock left at recent sales pace): " + "; ".join(
        f"{s['sku_name'] or s['sku_code']} ~{s['days_of_cover']}d" for s in items) + ".",
        "computed", [e.id for e in ev]),
        Claim("Cover is estimated from recent sales velocity, not a supplier lead-time plan.", "inference",
              assumption="days-of-cover = stock on hand / recent daily sales")]
    return Answer(q, "reorder_alert",
                  f"{len(items)} fast-moving item(s) are low on stock — soonest to run out: {items[0]['sku_name'] or items[0]['sku_code']} (~{items[0]['days_of_cover']}d).",
                  "PROBABLE", claims, ev, assumptions=["cover based on recent sales velocity"], data_used=["reorder_alert"])


def _h_turnover(conn, cid, q, entity, period=None) -> Answer:
    d = Q.get_inventory_turnover(conn, cid)
    if not d["turns"]:
        return _no_data(q, "inventory_turnover", "I need both stock value and recent sales to estimate turnover.")
    ev = [Evidence("to_turns", "Stock turns (annual)", d["turns"], f"{d['turns']}x"),
          Evidence("to_inv", "Stock value", d["inventory_value"], inr(d["inventory_value"]))]
    claims = [Claim(f"Your stock turns about {d['turns']}x a year (~{d['dio_days']} days of stock), on {inr(d['inventory_value'])} held.",
                    "computed", ["to_turns", "to_inv"]),
              Claim("This is a sales-based proxy; true turnover uses cost of goods, which isn't in the data yet.", "inference",
                    assumption="turns = annualised sales / stock value (no COGS)")]
    return Answer(q, "inventory_turnover", f"Stock turns roughly {d['turns']}x a year (~{d['dio_days']} days of cover).",
                  "PROBABLE", claims, ev, assumptions=["sales-based proxy, not COGS-based"],
                  data_used=["inventory_turnover"],
                  what_i_dont_know=["cost of goods (needed for a precise turnover figure)"])


def _h_sales_by_category(conn, cid, q, entity, period=None) -> Answer:
    w = _win(period)
    d = Q.get_sales_by_category(conn, cid, **w)
    cats = d.get("categories", [])[:6]
    when = _when(period, "overall")
    if not cats:
        return _no_data(q, "sales_by_category", f"I don't see categorised sales {when}.")
    ev = [Evidence(f"ct_{i}", c["category"], c["revenue"], f"{inr(c['revenue'])} ({c['pct']:.0f}%)") for i, c in enumerate(cats)]
    claims = [Claim("Sales by category: " + "; ".join(f"{c['category']} {inr(c['revenue'])} ({c['pct']:.0f}%)" for c in cats) + ".",
                    "computed", [e.id for e in ev])]
    chart = {"title": "Sales by category", "unit": "₹",
             "items": [{"name": c["category"], "value": c["revenue"], "display": inr(c["revenue"])} for c in cats]}
    return Answer(q, "sales_by_category", f"Your biggest category is {cats[0]['category']} at {cats[0]['pct']:.0f}% of sales.",
                  "CERTAIN", claims, ev, data_used=["sales_by_category"], chart=chart)


HANDLERS: dict[str, Callable] = {
    "business_pulse": _h_business_pulse, "collections_priority": _h_collections, "dso": _h_dso,
    "customer_changes": _h_customer_changes, "customer_movement": _h_customer_movement,
    "reorder_alert": _h_reorder, "inventory_turnover": _h_turnover, "sales_by_category": _h_sales_by_category,
    "concentration": _h_concentration, "top_customers": _h_top_customers, "revenue": _h_revenue,
    "revenue_trend": _h_revenue_trend, "receivables": _h_receivables, "payment_stretch": _h_payment_stretch,
    "dead_stock": _h_dead_stock, "top_skus": _h_top_skus, "least_skus": _h_least_skus,
    "purchases": _h_purchases, "inventory": _h_inventory,
    "overdue_pos": _h_overdue_pos, "overdue_orders": _h_overdue_orders, "margin": _h_margin,
    "forecast": _h_forecast, "creditworthy": _h_creditworthy,
}


def _no_data(q, intent, msg) -> Answer:
    return Answer(q, intent, msg, "UNCERTAIN",
                  [Claim(msg, "unknown")], [], what_i_dont_know=[msg])


def _unknown(q) -> Answer:
    return Answer(q, "unknown",
                  "I can't map that question yet. I can answer about revenue, customers, receivables, "
                  "payment terms, inventory, purchases, and overdue orders/POs.",
                  "UNCERTAIN", [Claim("Question not recognised by the router.", "unknown")], [],
                  what_i_dont_know=["how to map this question to the available data"])


# ── validation (deterministic post-check) ─────────────────────────────────────
def _validate(ans: Answer) -> Answer:
    """Every `computed` claim must trace to a real evidence id. Otherwise the
    claim is downgraded to inference (it can't be proven from given numbers)."""
    valid_ids = {e.id for e in ans.evidence}
    for c in ans.claims:
        if c.type == "computed":
            if not c.evidence or not all(e in valid_ids for e in c.evidence):
                c.type = "inference"
                c.assumption = (c.assumption or "could not be traced to a retrieved number")
    ans.data_used = sorted(set(ans.data_used))
    return ans


# ── gates ─────────────────────────────────────────────────────────────────────
def _gates(ans: Answer) -> Answer:
    has_computed = any(c.type == "computed" for c in ans.claims)
    has_unknown = any(c.type == "unknown" for c in ans.claims)
    data_gate = "pass" if (ans.evidence or has_computed) else "fail"
    rule_gate = "pass" if ans.intent != "unknown" else "fail"
    # Confidence is set by handlers; enforce the floor here.
    if data_gate == "fail" or rule_gate == "fail" or (has_unknown and not has_computed):
        ans.confidence = "UNCERTAIN"
    ans.gates = {"data": data_gate, "rule": rule_gate, "confidence": ans.confidence}
    return ans


# ── orchestrator ──────────────────────────────────────────────────────────────
# Intents whose answers involve judgment/analysis → always use the strong model.
SMART_INTENTS = {"concentration", "payment_stretch", "dead_stock", "creditworthy",
                 "forecast", "margin", "revenue_trend", "business_pulse", "dso",
                 "customer_changes", "customer_movement", "inventory_turnover"}

INTENT_DESCRIPTIONS = {
    "business_pulse": "a short overall snapshot / health briefing of the business",
    "collections_priority": "which overdue customers to chase first",
    "dso": "how many days it takes to get paid (days sales outstanding)",
    "customer_changes": "which customers grew or shrank vs last period",
    "customer_movement": "new customers and customers who stopped buying / churn",
    "reorder_alert": "items about to run out of stock",
    "inventory_turnover": "how fast stock is moving / turnover / days of stock",
    "sales_by_category": "sales split by product category",
    "concentration": "customer concentration / dependence / risk",
    "top_customers": "who the biggest customers are",
    "revenue": "total sales / revenue for a period",
    "revenue_trend": "how revenue changed over months",
    "receivables": "who owes money / outstanding / overdue payments",
    "payment_stretch": "customers paying beyond their agreed terms",
    "dead_stock": "stock not moving / dead stock",
    "top_skus": "best-selling products",
    "least_skus": "least-selling / worst-performing products that still sold (not zero-sale dead stock)",
    "purchases": "purchase spend / vendors",
    "inventory": "total stock value",
    "overdue_pos": "overdue purchase orders",
    "overdue_orders": "sales orders late to deliver",
    "margin": "profit margin / profitability",
    "forecast": "predicting the future / next quarter",
    "creditworthy": "whether a customer is safe to extend credit",
}


def answer(conn, company_id: str, question: str, use_llm: bool = True) -> dict:
    """Answer a business question. `use_llm=False` forces the deterministic path
    (used by the eval harness — fast, free, reproducible; the LLM only changes
    wording, never the validated numbers the harness checks)."""
    from datetime import date
    from vinayak.reasoning.dates import parse_period
    from vinayak.reasoning import llm

    llm_on = use_llm and llm.is_active()
    intent = classify(question)
    routed_by = "keywords"
    escalate = False
    # If the keyword router can't place it, let Claude pick. A question the
    # keyword router couldn't classify is, by definition, off the beaten path —
    # so we use the strong model for both the routing and the phrasing.
    if intent == "unknown" and llm_on:
        guess = llm.route(question, list(INTENT_DESCRIPTIONS.items()), model=llm.model_smart())
        if guess and guess in HANDLERS:
            intent, routed_by, escalate = guess, "claude", True

    entity = _entity_in(question, conn, company_id)
    period = parse_period(question, date.today())
    handler = HANDLERS.get(intent)
    ans = handler(conn, company_id, question, entity, period) if handler else _unknown(question)
    if period:
        ans.assumptions = list(dict.fromkeys(ans.assumptions + [f"time period: {period['label']}"]))
    ans = _validate(ans)
    ans = _gates(ans)

    # Model tier: Haiku for simple factual lookups; Sonnet when the answer needs
    # analysis / judgment / honesty (anything not a clean CERTAIN fact, or the
    # intents that carry inference, or an off-router question).
    needs_thought = (
        escalate
        or intent in SMART_INTENTS
        or ans.confidence != "CERTAIN"
        or any(c.type in ("inference", "unknown") for c in ans.claims)
    )
    model = llm.model_smart() if needs_thought else llm.model_fast()

    phrased_by, model_used, blocked = "template", None, False
    if llm_on:
        ctx = _consultant_context(conn, company_id, entity)   # brand-scoped profile + facts
        new_text = llm.phrase(ans, model=model, context=ctx)
        # The numeric guard: reject any LLM prose that surfaces a rupee figure we
        # didn't compute. On a block, give it ONE self-correcting retry before
        # falling back to the safe deterministic answer.
        if new_text and new_text != ans.answer and not _numbers_supported(new_text, ans):
            new_text = llm.phrase(ans, model=model, context=ctx, retry=True)
        if new_text and new_text != ans.answer and _numbers_supported(new_text, ans):
            ans.answer = new_text
            phrased_by = "claude"
            model_used = model
        elif new_text and new_text != ans.answer:
            blocked = True

    out = ans.to_dict()
    out["meta"] = {"routed_by": routed_by, "phrased_by": phrased_by,
                   "ai_active": llm.is_active(), "model": model_used,
                   "tier": ("smart" if needs_thought else "fast") if phrased_by == "claude" else None,
                   "numeric_guard": "blocked" if blocked else "ok"}
    return out


def _consultant_context(conn, company_id: str, entity: str | None) -> dict:
    """Brand-scoped context the analyst persona reasons with: the business
    profile and the active memory facts (for the entity in question, if any).
    Always filtered by company_id — never mixes brands."""
    try:
        from vinayak.memory import store as M
        profile = M.get_profile(conn, company_id) or {}
        entity_ref = f"customer:{entity}" if entity else None
        facts = M.active_facts(conn, company_id, entity_ref) if entity_ref else \
            M.active_facts(conn, company_id)[:8]
        fact_lines = [
            f"{f['entity_ref']} {f['claim_key']} = {f['claim_value']}"
            + (" (STALE — verify)" if f["status"] == "stale" else "")
            for f in facts
        ]
        return {
            "industry": profile.get("industry"),
            "sub_vertical": profile.get("sub_vertical"),
            "fiscal_year_start": profile.get("fiscal_year_start"),
            "healthy_margin_pct": profile.get("healthy_margin_pct"),
            "seasonality": profile.get("seasonality"),
            "facts": fact_lines,
        }
    except Exception:
        return {}


