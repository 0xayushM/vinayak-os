"""
reasoning/engine/router.py
───────────────────────────
Intent routing for the deterministic engine: the keyword table (INTENTS), the
classifier, follow-up detection, and best-effort entity matching. Self-contained
(only needs `re`); the pipeline and handlers import from here.
"""
from __future__ import annotations

import re


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
                          "compare month", "month by month", "growth", "grew", "6 month", "monthly",
                          "every month", "each month", "month wise", "monthwise", "month-wise",
                          "per month", "difference between month", "monthly difference",
                          "difference between sales", "month on month"]),
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


# ── follow-up detection (multi-turn) ──────────────────────────────────────────
_FOLLOWUP_RE = re.compile(
    r"\b(those|them|these|they|it|that one|the same|which of|what about|how about|"
    r"of these|of those|among (?:them|those)|and (?:what|which|who|how)|why|"
    r"break (?:that|it|this) down|the first one|the biggest one)\b",
    re.IGNORECASE,
)


def _looks_followup(question: str) -> bool:
    """Heuristic: does this question depend on the conversation before it?
    True for pronoun/ellipsis references or very short fragments."""
    q = (question or "").strip()
    return bool(_FOLLOWUP_RE.search(q)) or len(q.split()) <= 3


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
