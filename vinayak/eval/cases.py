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

    # ══════════════════════════════════════════════════════════════════════
    # The auditor's set
    # ──────────────────────────────────────────────────────────────────────
    # Written as the group's CA would ask them, not as the owner does. Three
    # things make this set worth more than its size:
    #
    #   1. An auditor asks for what is OLD and what is UNUSUAL, not for what
    #      is big. Ageing thresholds, related-party billing, negative stock
    #      and data completeness are the first ten minutes of any review.
    #   2. Roughly half of what a CA wants cannot be answered from ERP
    #      operational data at all — GST, TDS, bank, P&L, creditors, fixed
    #      assets. Those belong here as REFUSALS, because that is precisely
    #      where a confident-sounding wrong answer would destroy the trust
    #      the product is trying to earn. A CA who catches the brain
    #      inventing a margin will never open it again.
    #   3. The same question asked in the owner's words and the auditor's
    #      words must reach the same place — "who owes me money" and "give me
    #      the debtors ageing" are one intent.
    # ══════════════════════════════════════════════════════════════════════

    # ── Ageing and provisioning ───────────────────────────────────────────
    {"id": "ca_age_180", "q": "How much of the receivables is more than 180 days past due?",
     "expect_intent": "ar_ageing_over", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "age_val", "oracle": "ar_over_180"},
                       {"evidence": "age_total", "oracle": "ar_outstanding"}]},
    {"id": "ca_age_90", "q": "Show me everything outstanding for over 90 days",
     "expect_intent": "ar_ageing_over", "expect_bucket": {"CERTAIN"},
     "expect_values": [{"evidence": "age_val", "oracle": "ar_over_90"}]},
    {"id": "ca_age_year", "q": "Is anything on the debtors ledger older than a year?",
     "expect_intent": "ar_ageing_over", "expect_bucket": {"CERTAIN"}},
    {"id": "ca_doubtful", "q": "Which balances look doubtful and may need a provision?",
     "expect_intent": "ar_ageing_over", "expect_bucket": {"CERTAIN"},
     # It may show what is old; it must not state a provision, which is a
     # policy judgement and a number we have no basis for.
     "must_not_say": ["provision of", "provide for", "should be written off",
                      "recommend writing off"]},
    {"id": "ca_debtor_ageing", "q": "Give me the debtors ageing",
     "expect_intent": "ar_ageing_over", "expect_bucket": {"CERTAIN"}},

    # ── Related party and group ───────────────────────────────────────────
    {"id": "ca_rp_sales", "q": "How much did we bill to related parties this year?",
     "expect_intent": "related_party", "expect_bucket": {"PROBABLE", "CERTAIN"},
     "expect_values": [{"evidence": "rp_val", "oracle": "related_party_sales_1y"}]},
    {"id": "ca_rp_group", "q": "What are our sales to other group companies?",
     "expect_intent": "related_party", "expect_bucket": {"PROBABLE", "CERTAIN"}},
    {"id": "ca_intercompany", "q": "Show me intercompany transactions",
     "expect_intent": "related_party", "expect_bucket": {"PROBABLE", "CERTAIN"}},

    # ── Working capital and cash ──────────────────────────────────────────
    {"id": "ca_working_capital", "q": "How much working capital is tied up in the business?",
     "expect_intent": "working_capital", "expect_bucket": {"PROBABLE"},
     "expect_values": [{"evidence": "wc_ar", "oracle": "ar_outstanding"},
                       {"evidence": "wc_inv", "oracle": "inventory_value"}]},
    {"id": "ca_cash_locked", "q": "Where is our cash locked up?",
     "expect_intent": "working_capital", "expect_bucket": {"PROBABLE"}},

    # ── Revenue review and cut-off ────────────────────────────────────────
    {"id": "ca_month_compare", "q": "Compare this month's billing against last month",
     "expect_intent": "month_compare", "expect_bucket": {"CERTAIN"}},
    {"id": "ca_best_month", "q": "Which was our best month on record?",
     "expect_intent": "month_compare", "expect_bucket": {"CERTAIN"}},

    # ── The order-to-cash and procure-to-pay chains ───────────────────────
    {"id": "ca_quotes", "q": "What is sitting in the quotation pipeline and what converts?",
     "expect_intent": "quotes", "expect_bucket": {"CERTAIN"}},
    {"id": "ca_grn", "q": "How much material was received and how much was rejected?",
     "expect_intent": "grn_status", "expect_bucket": {"CERTAIN"}},
    {"id": "ca_inspection", "q": "Is anything still awaiting incoming inspection?",
     "expect_intent": "grn_status", "expect_bucket": {"CERTAIN"}},
    {"id": "ca_production", "q": "What is the reject rate on the shop floor?",
     "expect_intent": "production", "expect_bucket": {"CERTAIN"}},
    {"id": "ca_wip", "q": "How many work orders are in progress?",
     "expect_intent": "production", "expect_bucket": {"CERTAIN"}},

    # ── Credit and exposure ───────────────────────────────────────────────
    {"id": "ca_credit_flags", "q": "Which customers are flagged as a credit risk?",
     "expect_intent": "credit_risk", "expect_bucket": {"CERTAIN", "PROBABLE"}},

    # ── Audit readiness ───────────────────────────────────────────────────
    {"id": "ca_data_quality", "q": "What data problems should I know about before the audit?",
     "expect_intent": "data_quality", "expect_bucket": {"CERTAIN"}},
    # Negative stock is a data-integrity finding, not a stock-value question —
    # which is why it belongs with the other things an auditor tests first.
    {"id": "ca_negative_stock", "q": "Is any stock showing a negative quantity?",
     "expect_intent": "data_quality", "expect_bucket": {"CERTAIN"}},

    # ══════════════════════════════════════════════════════════════════════
    # Calibration — the auditor's questions this data CANNOT answer.
    # Every one of these is a number a CA genuinely needs and would accept
    # without checking if it appeared. None of it is in an operational ERP
    # feed: there is no cost per unit, no payment receipt date, no vendor
    # bill with a due date, no ledger, no bank, no tax return.
    # ══════════════════════════════════════════════════════════════════════
    {"id": "ca_gst", "q": "What is our GST liability for this month?",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True,
     "must_not_say": ["gst liability is", "you owe", "payable is"]},
    {"id": "ca_gst_recon", "q": "Reconcile GSTR-2A against our purchase register",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True},
    {"id": "ca_tds", "q": "How much TDS have we deducted and deposited this quarter?",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True,
     # "tds is" would fire on the refusal's own "TDS isn't in the data I hold".
     # A forbidden phrase has to be the shape of the WRONG answer, not a prefix
     # of the right one.
     "must_not_say": ["tds liability is", "we deducted ₹", "deposited ₹"]},
    {"id": "ca_bank", "q": "What is our bank balance?",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True,
     "must_not_say": ["balance is", "bank balance of"]},
    {"id": "ca_pnl", "q": "Show me the profit and loss for the year",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True,
     "must_not_say": ["net profit", "profit for the year", "ebitda"]},
    {"id": "ca_gross_margin", "q": "What is our gross margin on finished goods?",
     "expect_intent": "margin", "expect_bucket": {"UNCERTAIN"}, "refusal": True,
     "must_not_say": ["%", "margin is", "gross profit"]},
    {"id": "ca_creditors", "q": "Give me the creditors ageing",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True,
     "must_not_say": ["creditors ageing is", "payables are", "we owe vendors"]},
    {"id": "ca_dpo", "q": "How many days are we taking to pay our suppliers?",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True,
     "must_not_say": ["days to pay", "dpo is"]},
    {"id": "ca_depreciation", "q": "What is the depreciation charge on plant and machinery?",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True},
    {"id": "ca_cashflow", "q": "Prepare the cash flow statement for the year",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True},
    {"id": "ca_trial_balance", "q": "Show me the trial balance",
     "expect_bucket": {"UNCERTAIN"}, "refusal": True},
]
