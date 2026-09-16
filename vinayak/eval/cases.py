"""
eval/cases.py
──────────────
The golden test set — our substitute for Cursor's compiler. Each case fixes an
expectation the reasoning engine must keep meeting as prompts/models/routing
change. Grouped into:

  • answerable   — expect a confident, grounded answer of a specific intent
  • calibration  — UNANSWERABLE from data; the engine MUST refuse (UNCERTAIN)
  • memory       — seed a fact, then check the engine uses it (PROBABLE + flag)
  • must_not_say — the engine must NOT utter these (hallucination / overconfidence)

This list is seeded from the Phase-0 owner questions and grows every time the AI
gets something wrong in practice (per the product doc). Run via the harness.

Case fields:
  id, q                 — the question
  companies             — which sandbox brands it applies to (default: both)
  expect_intent         — the intent the router should pick (optional)
  expect_bucket         — allowed confidence labels (set)
  refusal               — True if the right answer is "I can't" (UNCERTAIN)
  must_not_say          — substrings that, if present, are a failure
  seed_facts            — facts to write before asking (for memory tests)
  expect_values         — [{evidence, oracle, tolerance_pct?}] — the FACTUAL
                          check. Each names an Evidence id the answer must
                          carry and an oracle in eval/oracles.py that computes
                          the same fact independently. This is what makes
                          "≥ 80% factual accuracy" a measured number rather
                          than an assertion.

Only facts with a window-free definition are graded — total outstanding, stock
value, overdue counts, and identities like the largest debtor. Revenue "in the
period" is not graded, because the period is the engine's choice and an oracle
that re-derived it would be copying the thing it is meant to check. See
eval/oracles.py for why that trade is the honest one.
"""
from __future__ import annotations

BOTH = ["kbrushes", "protegere"]

CASES: list[dict] = [
    # ── Answerable (grounded, specific intent) ───────────────────────────────
    {"id": "rev_period", "q": "How much did I sell recently?",
     "expect_intent": "revenue", "expect_bucket": {"CERTAIN"}},
    {"id": "rev_trend", "q": "How did revenue move over the last 6 months?",
     "expect_intent": "revenue_trend", "expect_bucket": {"CERTAIN", "UNCERTAIN"}},
    {"id": "top_cust", "q": "Who are my top customers?",
     "expect_intent": "top_customers", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "cust_0", "oracle": "top_customer_1y", "field": "label"}]},
    {"id": "concentration", "q": "Which customers are most of my sales? Am I too dependent on them?",
     "expect_intent": "concentration", "expect_bucket": {"CERTAIN", "PROBABLE"},
     "expect_values": [{"evidence": "conc_top", "oracle": "top_customer_1y", "field": "label"}]},
    {"id": "receivables", "q": "Who owes me money and who is overdue?",
     "expect_intent": "receivables", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "ar_total", "oracle": "ar_outstanding"},
                       {"evidence": "ar_overdue", "oracle": "ar_overdue"},
                       {"evidence": "exp_0", "oracle": "ar_biggest_debtor", "field": "label"}]},
    {"id": "purchases", "q": "How much am I spending on purchases and with whom?",
     "expect_intent": "purchases", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "ven_0", "oracle": "top_vendor_1y", "field": "label"}]},
    {"id": "overdue_pos", "q": "Which purchase orders are overdue?",
     "expect_intent": "overdue_pos", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "po_n", "oracle": "overdue_po_count"}]},
    {"id": "overdue_orders", "q": "Which sales orders are late to deliver?",
     "expect_intent": "overdue_orders", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "oo_n", "oracle": "overdue_order_count"}]},
    {"id": "top_skus", "q": "Which products make me the most money?",
     "expect_intent": "top_skus", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "sk_0", "oracle": "top_sku_1y", "field": "label"}]},
    {"id": "least_skus", "q": "list the least selling SKUs till now",
     "expect_intent": "least_skus", "expect_bucket": {"CERTAIN"},
     "must_not_say": ["best-selling", "best selling", "make me the most"]},
    {"id": "least_skus2", "q": "what are my worst selling products?",
     "expect_intent": "least_skus", "expect_bucket": {"CERTAIN"}},
    {"id": "inventory", "q": "How much stock value am I holding?",
     "expect_intent": "inventory", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "inv_val", "oracle": "inventory_value"},
                       {"evidence": "inv_skus", "oracle": "inventory_sku_count"}]},
    {"id": "dead_stock", "q": "What stock is just sitting there?",
     "expect_intent": "dead_stock", "expect_bucket": {"PROBABLE"}},

    # ── Wave 1 analytical intents ────────────────────────────────────────────
    {"id": "pulse", "q": "give me an overview of my business",
     "expect_intent": "business_pulse", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "p_ar", "oracle": "ar_outstanding"},
                       {"evidence": "p_overdue", "oracle": "ar_overdue"}]},
    {"id": "collections", "q": "who should I chase for payments first?",
     "expect_intent": "collections_priority", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "co_total", "oracle": "ar_overdue"},
                       {"evidence": "co_0", "oracle": "ar_most_overdue_customer",
                        "field": "label"}]},
    {"id": "dso", "q": "how long is it taking to get paid?",
     "expect_intent": "dso", "expect_bucket": {"PROBABLE", "UNCERTAIN"},
     "expect_values": [{"evidence": "dso_ar", "oracle": "ar_outstanding"}]},
    {"id": "cust_changes", "q": "which customers grew or shrank?",
     "expect_intent": "customer_changes", "expect_bucket": {"CERTAIN", "UNCERTAIN"}},
    {"id": "cust_movement", "q": "any customers that stopped buying?",
     "expect_intent": "customer_movement", "expect_bucket": {"CERTAIN", "UNCERTAIN"}},
    {"id": "reorder", "q": "what am I about to run out of?",
     "expect_intent": "reorder_alert", "expect_bucket": {"PROBABLE"}},
    {"id": "turnover", "q": "how fast is my stock moving?",
     "expect_intent": "inventory_turnover", "expect_bucket": {"PROBABLE", "UNCERTAIN"},
     "expect_values": [{"evidence": "to_inv", "oracle": "inventory_value"}]},
    {"id": "by_category", "q": "show me sales by category",
     "expect_intent": "sales_by_category", "expect_bucket": {"CERTAIN"}},
    {"id": "dead_real", "q": "what stock is just sitting there?",
     "expect_intent": "dead_stock", "expect_bucket": {"PROBABLE"},
     "must_not_say": ["best selling", "highest-value stock"]},

    # ── Calibration — must REFUSE (data can't answer) ────────────────────────
    {"id": "margin", "q": "What is my profit margin on product X?",
     "expect_intent": "margin", "expect_bucket": {"UNCERTAIN"}, "refusal": True,
     "must_not_say": ["%", "margin is", "profit is"]},
    {"id": "forecast", "q": "Will next quarter be weak?",
     "expect_intent": "forecast", "expect_bucket": {"UNCERTAIN"}, "refusal": True},
    {"id": "creditworthy", "q": "Is DEV COLOUR safe to extend credit to?",
     "companies": ["kbrushes"], "expect_intent": "creditworthy",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True},
    {"id": "nonsense", "q": "What colour should I paint the office?",
     "expect_intent": "unknown", "expect_bucket": {"UNCERTAIN"}, "refusal": True},
    {"id": "out_of_scope", "q": "How many employees should I hire next year?",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True},

    # ── Memory — without a fact it must NOT guess; with a fact it must use it ─
    {"id": "stretch_no_fact", "q": "Is any customer stretching their payment terms?",
     "expect_intent": "payment_stretch", "expect_bucket": {"UNCERTAIN", "PROBABLE"}},
    {"id": "stretch_with_fact", "q": "Is any customer stretching their payment terms?",
     "companies": ["kbrushes"], "expect_intent": "payment_stretch",
     "expect_bucket": {"PROBABLE"},
     "seed_facts": [{"entity_type": "customer",
                     "entity_ref": "customer:DEV COLOUR AND COATINGS PVT LTD",
                     "claim_key": "payment_terms_days", "claim_value": 7}]},
]
