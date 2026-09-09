"""
adapters/tranzact/reports.py
─────────────────────────────
Canonical map of TranzAct report IDs → human names.
Used by every pipeline and by sync logging.

⚠️  Do not change report IDs after the schema lock (end of Week 1).
    These IDs are the foreign key between TranzAct and our Postgres tables.
"""

# ── Report ID registry ───────────────────────────────────────────────────────

REPORT_IDS: dict[str, str] = {
    "sales_invoices":       "29",
    "ar_aging":             "102",
    "sales_orders":         "2",
    "purchase_invoices":    "77",
    "purchase_orders":      "3",
    "grn_qir":              "34",
    "sales_quotations":     "8",
    "inventory_valuation":  "9",
    "process_routing":      "86",
    "process_details":      "25",
}

# Reverse map: report_id string → pipeline name
REPORT_ID_TO_NAME: dict[str, str] = {v: k for k, v in REPORT_IDS.items()}

# ── Report FUNCTION names (the stable key since TranzAct's Aug-2026 re-keying) ─
# On 11 Aug 2026 TranzAct replaced the small integer report ids above with
# per-company UUIDs, and /generate_report began returning HTTP 500 for the old
# ids (instead of a clean 404). The UUIDs are NOT stable across companies, but
# each report's `function_name` (from GET reporting/get_reports) is. So:
#   • the legacy numeric ids stay as the pipeline label used in sync-run logs
#     (tz_sync_runs.report_id is an integer column), and
#   • at fetch time the client resolves legacy id → function_name → live UUID
#     via the account's report catalog (see client.resolve_report_id).
# Verified against the live catalog on 2026-09-07 (all ten return data).
REPORT_FUNCTIONS: dict[str, str] = {
    "sales_invoices":       "sales_invoice_item_register",       # Sales Invoice Register (Item-wise)
    "ar_aging":             "accounts_receivable",               # Accounts Receivable
    "sales_orders":         "oc_item_report",                    # Order Confirmation / SO Register (Item-wise)
    "purchase_invoices":    "purchase_invoice_itemwise_register",# Purchase Invoice Register (Item-wise)
    "purchase_orders":      "po_report",                         # Purchase Order Register
    "grn_qir":              "qir_inward_item",                   # GRN/QIR Register (Item-wise)
    "sales_quotations":     "sales_quotation_item_report",       # Sales Quotation Register (Item-wise)
    "inventory_valuation":  "product_details",                   # Product Price and Inventory
    "process_routing":      "item_bom",                          # Item BOM (the routing master: FG → BOM → item)
    "process_details":      "process_report",                    # Process Details (Item-wise)
}

# legacy numeric id → function_name (what the client uses to resolve a live UUID)
LEGACY_ID_TO_FUNCTION: dict[str, str] = {
    REPORT_IDS[name]: fn for name, fn in REPORT_FUNCTIONS.items()
}

# NOTE: TranzAct's /generate_report has no usable server-side date filter — every
# probed shape returned the full report — so pipelines fetch the COMPLETE report
# each run (see vinayak/adapters/tranzact/client.py). There is therefore no
# date-window helper here anymore.
