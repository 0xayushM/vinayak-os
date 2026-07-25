"""
canonical/zoho_canonical.py
────────────────────────────
⚠️  PROVISIONAL — built to the DOCUMENTED Zoho Books REST API v3 (the field names
    below are the real API fields the zb_* ingestion already targets), but NOT yet
    verified against a live Zoho org. Treat the mapping as a draft until we have an
    account and can reconcile against real responses. It is fully isolated behind
    source='zoho' and only runs for Zoho workspaces, so it cannot affect the live
    TranzAct path.

    OPEN DECISION — line items:  Zoho's LIST endpoint (GET /invoices) returns
    invoice HEADERS only; line items come only from the per-invoice DETAIL
    endpoint (GET /invoices/{id}). The current ingestion uses the list endpoint,
    so zb_invoices/zb_bills have no line breakdown — which is why this mapper
    SYNTHESISES one line per document (see zoho_invoice_line_fields). Revenue/spend
    reconcile at the invoice level, but there is NO SKU-level Zoho revenue until we
    decide whether to also pull invoice details into a zb_invoice_lines table.
    Revisit that (cost of N detail calls vs. value) once the org exists.

The SECOND SourceAdapter: maps the Zoho Books zb_* tables into the SAME canonical
schema the TranzAct adapter targets — a Zoho-only workspace is served entirely
from canon_* with ZERO changes to any query function.

Shape differences handled here (Zoho vs TranzAct):
  • Zoho invoices/bills are HEADER-LEVEL (no line items in the API we ingest).
    The canonical model is line-grain, so we synthesise ONE line per invoice/bill
    carrying the whole document's goods value (sub_total). SKU-level panels then
    show a single blank bucket for Zoho — honest, since the breakdown isn't in
    the source. Revenue/spend totals reconcile at the invoice level.
  • AR is derived, not a separate report: every unpaid invoice (balance > 0)
    becomes a canon_payment row, with days_overdue + aging_bucket COMPUTED from
    due_date (same 0-30/31-60/61-90/90+ boundaries as the TranzAct AR pipeline).
  • purchase_rate on items gives real unit cost (canonical inventory valuation).

Idempotent: every canonical row upserts on (company_id, source='zoho', source_ref),
where source_ref is the Zoho object id. Anything unmappable → ingest_issues.

Usage:
    from vinayak.canonical.zoho_canonical import rebuild_canonical_zoho
    rebuild_canonical_zoho(conn, company_id)
    # or:  python -m vinayak.canonical.zoho_canonical [company_id ...]
"""
from __future__ import annotations

import logging
import sys
from datetime import date

from vinayak.canonical.base import LoadStats, Unmapped, log_issue, upsert_canon

logger = logging.getLogger(__name__)
SOURCE = "zoho"


# ── pure helpers ──────────────────────────────────────────────────────────────
def _f(v):
    """Coerce to float, preserving None."""
    return float(v) if v is not None else None


def days_overdue_and_bucket(due_date, today: date | None = None) -> tuple[int | None, str | None]:
    """days_overdue = max(0, today - due_date); bucket 0-30/31-60/61-90/90+.
    Mirrors the TranzAct AR aging boundaries exactly. Returns (None, None) with no
    due date."""
    if due_date is None:
        return None, None
    today = today or date.today()
    d = max(0, (today - due_date).days)
    if d <= 30:
        bucket = "0-30"
    elif d <= 60:
        bucket = "31-60"
    elif d <= 90:
        bucket = "61-90"
    else:
        bucket = "90+"
    return d, bucket


# ── pure field builders (one per canonical object) ────────────────────────────
def zoho_customer_fields(zoho_id, contact_name, company_name, payment_terms,
                         outstanding_receivable) -> dict:
    return {
        "source_ref": zoho_id, "confidence": 1.0, "raw": None,
        "name": contact_name or company_name, "customer_code": zoho_id,
        "credit_limit": None,
        "payment_terms_days": int(payment_terms) if payment_terms is not None else None,
        "outstanding": _f(outstanding_receivable), "risk_score": None,
    }


def zoho_invoice_header_fields(zoho_id, invoice_number, invoice_date, due_date,
                               customer_id, customer_name, sub_total, tax_total,
                               total, status) -> dict:
    return {
        "source_ref": zoho_id, "confidence": 1.0, "raw": None,
        "invoice_number": invoice_number, "invoice_date": invoice_date, "due_date": due_date,
        "customer_ref": customer_id, "customer_name": customer_name,
        "gross": _f(sub_total) or 0.0, "tax": _f(tax_total) or 0.0, "net": _f(total) or 0.0,
        "status": status, "salesperson": None,
    }


def zoho_invoice_line_fields(zoho_id, invoice_number, sub_total, invoice_id) -> dict:
    """One synthetic line carrying the whole invoice's goods value (ex-tax).
    TODO(zoho): replace with real line items once/if we ingest invoice details
    (GET /invoices/{id}) into a zb_invoice_lines table — see the module header."""
    return {
        "source_ref": zoho_id, "raw": None, "invoice_id": invoice_id,
        "invoice_number": invoice_number, "sku": None, "sku_name": None, "category": None,
        "quantity": None, "unit_price": None, "line_total": _f(sub_total) or 0.0,
    }


def zoho_payment_fields(zoho_id, customer_id, customer_name, invoice_number,
                        invoice_date, due_date, total, balance,
                        today: date | None = None) -> dict:
    outstanding = _f(balance) or 0.0
    days, bucket = days_overdue_and_bucket(due_date, today)
    return {
        "source_ref": zoho_id, "confidence": 1.0, "raw": None,
        "customer_ref": customer_id, "customer_name": customer_name,
        "invoice_number": invoice_number, "invoice_date": invoice_date, "due_date": due_date,
        "invoice_amount": _f(total) or 0.0, "outstanding_amount": outstanding,
        "days_overdue": days, "aging_bucket": bucket,
        "mode": None, "reconciled": outstanding == 0,
    }


def zoho_item_fields(zoho_id, item_name, sku, category, purchase_rate, stock_on_hand) -> dict:
    qty = _f(stock_on_hand)
    cost = _f(purchase_rate)
    total_value = (qty * cost) if (qty is not None and cost is not None) else None
    return {
        "source_ref": zoho_id, "confidence": 1.0, "raw": None,
        "sku": sku, "sku_name": item_name, "category": category, "warehouse": None,
        "quantity": qty or 0.0, "qty_reserved": None,
        "unit_cost": cost or 0.0, "total_value": total_value or 0.0,
        "is_raw_material": None, "is_negative_stock": (qty is not None and qty < 0),
        "last_movement_date": None,
    }


def zoho_bill_header_fields(zoho_id, bill_number, bill_date, due_date, vendor_id,
                            vendor_name, sub_total, total, status) -> dict:
    sub = _f(sub_total) or 0.0
    grand = _f(total) or 0.0
    return {
        "source_ref": zoho_id, "confidence": 1.0, "raw": None,
        "invoice_number": bill_number, "invoice_date": bill_date, "due_date": due_date,
        "vendor_ref": vendor_id, "vendor_name": vendor_name,
        "gross": sub, "tax": max(0.0, grand - sub), "net": grand, "status": status,
    }


def zoho_bill_line_fields(zoho_id, bill_number, sub_total, invoice_id) -> dict:
    return {
        "source_ref": zoho_id, "raw": None, "invoice_id": invoice_id,
        "invoice_number": bill_number, "sku": None, "sku_name": None,
        "quantity": None, "unit_price": None, "line_total": _f(sub_total) or 0.0,
    }


# ── rebuild functions ─────────────────────────────────────────────────────────
def _rebuild_customers(cur, company_id: str) -> int:
    cur.execute("""
        SELECT zoho_id, contact_name, company_name, payment_terms, outstanding_receivable
        FROM zb_contacts
        WHERE company_id = %s AND (contact_type IS NULL OR contact_type ILIKE 'customer')
    """, (company_id,))
    rows = []
    for r in cur.fetchall():
        if not r[0]:
            log_issue(cur, company_id, SOURCE,
                      Unmapped("customer", "zoho_id", "missing_required", r[1]))
            continue
        rows.append(zoho_customer_fields(*r))
    return upsert_canon(cur, "canon_customer", company_id, SOURCE, rows)


def _rebuild_sales(cur, company_id: str) -> tuple[int, int]:
    cur.execute("""
        SELECT zoho_id, invoice_number, invoice_date, due_date, customer_id,
               customer_name, sub_total, tax_total, total, status
        FROM zb_invoices WHERE company_id = %s
    """, (company_id,))
    invoices = cur.fetchall()
    headers = []
    for r in invoices:
        if not r[0]:
            log_issue(cur, company_id, SOURCE,
                      Unmapped("sales_invoice", "zoho_id", "missing_required", r[1]))
            continue
        headers.append(zoho_invoice_header_fields(*r))
    n_head = upsert_canon(cur, "canon_sales_invoice", company_id, SOURCE, headers)

    cur.execute(
        "SELECT source_ref, id FROM canon_sales_invoice WHERE company_id = %s AND source = %s",
        (company_id, SOURCE),
    )
    id_of = {r[0]: r[1] for r in cur.fetchall()}

    lines = []
    for r in invoices:
        zoho_id, invoice_number, sub_total = r[0], r[1], r[6]
        if zoho_id not in id_of:
            continue
        lines.append(zoho_invoice_line_fields(zoho_id, invoice_number, sub_total, id_of[zoho_id]))
    n_line = upsert_canon(cur, "canon_sales_invoice_line", company_id, SOURCE, lines)
    return n_head, n_line


def _rebuild_payments(cur, company_id: str) -> int:
    # AR = every invoice still carrying a balance.
    cur.execute("""
        SELECT zoho_id, customer_id, customer_name, invoice_number,
               invoice_date, due_date, total, balance
        FROM zb_invoices
        WHERE company_id = %s AND COALESCE(balance, 0) > 0
    """, (company_id,))
    rows = []
    for r in cur.fetchall():
        if not r[0]:
            continue
        rows.append(zoho_payment_fields(*r))
    return upsert_canon(cur, "canon_payment", company_id, SOURCE, rows)


def _rebuild_inventory(cur, company_id: str) -> int:
    cur.execute("""
        SELECT zoho_id, item_name, sku, category, purchase_rate, stock_on_hand
        FROM zb_items WHERE company_id = %s
    """, (company_id,))
    rows = []
    for r in cur.fetchall():
        if not r[0]:
            log_issue(cur, company_id, SOURCE,
                      Unmapped("inventory_item", "zoho_id", "missing_required", r[1]))
            continue
        rows.append(zoho_item_fields(*r))
    return upsert_canon(cur, "canon_inventory_item", company_id, SOURCE, rows)


def _rebuild_purchases(cur, company_id: str) -> tuple[int, int]:
    cur.execute("""
        SELECT zoho_id, bill_number, bill_date, due_date, vendor_id, vendor_name,
               sub_total, total, status
        FROM zb_bills WHERE company_id = %s
    """, (company_id,))
    bills = cur.fetchall()
    headers = []
    for r in bills:
        if not r[0]:
            log_issue(cur, company_id, SOURCE,
                      Unmapped("purchase_invoice", "zoho_id", "missing_required", r[1]))
            continue
        headers.append(zoho_bill_header_fields(*r))
    n_head = upsert_canon(cur, "canon_purchase_invoice", company_id, SOURCE, headers)

    cur.execute(
        "SELECT source_ref, id FROM canon_purchase_invoice WHERE company_id = %s AND source = %s",
        (company_id, SOURCE),
    )
    id_of = {r[0]: r[1] for r in cur.fetchall()}

    lines = []
    for r in bills:
        zoho_id, bill_number, sub_total = r[0], r[1], r[6]
        if zoho_id not in id_of:
            continue
        lines.append(zoho_bill_line_fields(zoho_id, bill_number, sub_total, id_of[zoho_id]))
    n_line = upsert_canon(cur, "canon_purchase_invoice_line", company_id, SOURCE, lines)
    return n_head, n_line


# ── public entry point ────────────────────────────────────────────────────────
def rebuild_canonical_zoho(conn, company_id: str) -> LoadStats:
    """Rebuild canonical objects for one Zoho workspace from zb_* data.
    Single transaction; safe + idempotent."""
    stats = LoadStats()
    with conn.cursor() as cur:
        stats.upserted["customer"] = _rebuild_customers(cur, company_id)
        h, l = _rebuild_sales(cur, company_id)
        stats.upserted["sales_invoice"] = h
        stats.upserted["sales_invoice_line"] = l
        stats.upserted["payment"] = _rebuild_payments(cur, company_id)
        stats.upserted["inventory_item"] = _rebuild_inventory(cur, company_id)
        ph, pl = _rebuild_purchases(cur, company_id)
        stats.upserted["purchase_invoice"] = ph
        stats.upserted["purchase_invoice_line"] = pl
        cur.execute("SELECT COUNT(*) FROM ingest_issues WHERE company_id = %s AND source = %s",
                    (company_id, SOURCE))
        stats.issues = int(cur.fetchone()[0] or 0)
    # Reason once at ingest: refresh per-customer summaries (same transaction).
    from vinayak.memory.entity_summary import refresh_customer_summaries
    stats.upserted["entity_summary"] = refresh_customer_summaries(conn, company_id)
    conn.commit()
    logger.info("zoho canonical rebuilt for %s: %s (issues=%d)",
                company_id, stats.upserted, stats.issues)
    return stats


def _companies(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT company_id FROM zb_invoices ORDER BY 1")
        return [r[0] for r in cur.fetchall()]


if __name__ == "__main__":
    import os
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    targets = sys.argv[1:] or _companies(conn)
    for cid in targets:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ingest_issues WHERE company_id = %s AND source = %s",
                        (cid, SOURCE))
        conn.commit()
        s = rebuild_canonical_zoho(conn, cid)
        print(f"{cid}: {s.upserted}  issues={s.issues}")
    conn.close()
