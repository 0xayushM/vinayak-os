"""
canonical/tranzact_canonical.py
────────────────────────────────
The FIRST SourceAdapter: maps the (already-deduped) Tranzact-shaped tz_* tables
into the canonical schema for Slice-1 objects — Customer, SalesInvoice(+line),
InventoryItem, Payment(AR).

This is the moment the product stops being "a Tranzact tool" and becomes "an
engine that currently has one adapter." Adding Tally/Busy later means writing
another adapter against this same contract and touching zero query functions.

Idempotent: every canonical row upserts on (company_id, source, source_ref), so
re-running after each sync refreshes in place. Anything unmappable is logged to
ingest_issues — never guessed, never dropped.

Usage:
    from vinayak.canonical.tranzact_canonical import rebuild_canonical
    rebuild_canonical(conn, company_id)            # one company
    # or:  python -m vinayak.canonical.tranzact_canonical [company_id ...]
"""
from __future__ import annotations

import logging
import sys

import psycopg2.extras

from vinayak.canonical.base import LoadStats, Unmapped, log_issue
from vinayak.pipelines.helpers import num, stable_row_id

logger = logging.getLogger(__name__)
SOURCE = "tranzact"


# ── generic idempotent upsert ─────────────────────────────────────────────────
def _upsert(cur, table: str, company_id: str, rows: list[dict]) -> int:
    """Upsert canonical rows on (company_id, source, source_ref). rows carry
    source_ref, confidence, raw, and the typed columns."""
    if not rows:
        return 0
    # Collapse duplicate keys within the batch (last wins) so ON CONFLICT can't
    # hit the same row twice — source tables may still carry near-dupes.
    deduped: dict[str, dict] = {}
    for r in rows:
        deduped[r["source_ref"]] = r
    rows = list(deduped.values())
    cols = list(rows[0].keys())
    assert "source_ref" in cols
    col_sql = ", ".join(["company_id", "source"] + cols)
    set_sql = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "source_ref")
    values = [tuple([company_id, SOURCE] + [r[c] for c in cols]) for r in rows]
    template = "(" + ", ".join(["%s"] * (len(cols) + 2)) + ")"
    sql = (
        f"INSERT INTO {table} ({col_sql}) VALUES %s "
        f"ON CONFLICT (company_id, source, source_ref) "
        f"DO UPDATE SET {set_sql}, ingested_at = now()"
    )
    psycopg2.extras.execute_values(cur, sql, values, template=template, page_size=500)
    return len(values)


# ── object builders ───────────────────────────────────────────────────────────
def _rebuild_customers(cur, company_id: str) -> int:
    # Customer master from sales parties, enriched with AR outstanding.
    cur.execute("""
        SELECT COALESCE(customer_code, customer_name) AS key,
               MAX(customer_name) AS name, MAX(customer_code) AS code
        FROM tz_sales_invoices
        WHERE company_id = %s
        GROUP BY COALESCE(customer_code, customer_name)
    """, (company_id,))
    parties = cur.fetchall()

    cur.execute("""
        SELECT customer_name, COALESCE(SUM(outstanding_amount), 0)
        FROM tz_ar_aging WHERE company_id = %s GROUP BY customer_name
    """, (company_id,))
    outstanding = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

    rows = []
    for key, name, code in parties:
        if not key:
            log_issue(cur, company_id, SOURCE,
                      Unmapped("customer", "customer_code", "missing_identity", name))
            continue
        rows.append({
            "source_ref": str(key), "confidence": 1.0, "raw": None,
            "name": name, "customer_code": code,
            "credit_limit": None, "payment_terms_days": None,
            "outstanding": outstanding.get(name), "risk_score": None,
        })
    return _upsert(cur, "canon_customer", company_id, rows)


def _rebuild_sales(cur, company_id: str) -> tuple[int, int]:
    # Headers: aggregate the line-level tz table to one row per invoice.
    cur.execute("""
        SELECT invoice_number,
               MAX(invoice_date), MAX(due_date),
               MAX(customer_code), MAX(customer_name),
               COALESCE(SUM(line_total), 0)  AS gross,
               COALESCE(SUM(tax_amount), 0)  AS tax,
               MAX(invoice_total)            AS net,
               MAX(payment_status), MAX(salesperson)
        FROM tz_sales_invoices
        WHERE company_id = %s
        GROUP BY invoice_number
    """, (company_id,))
    headers = []
    for r in cur.fetchall():
        if not r[0]:
            log_issue(cur, company_id, SOURCE,
                      Unmapped("sales_invoice", "invoice_number", "missing_required", None))
            continue
        headers.append({
            "source_ref": r[0], "confidence": 1.0, "raw": None,
            "invoice_number": r[0], "invoice_date": r[1], "due_date": r[2],
            "customer_ref": r[3], "customer_name": r[4],
            "gross": float(r[5] or 0), "tax": float(r[6] or 0), "net": float(r[7] or 0),
            "status": r[8], "salesperson": r[9],
        })
    n_head = _upsert(cur, "canon_sales_invoice", company_id, headers)

    # Map invoice_number -> canonical header id for the FK on lines.
    cur.execute(
        "SELECT source_ref, id FROM canon_sales_invoice WHERE company_id = %s AND source = %s",
        (company_id, SOURCE),
    )
    id_of = {r[0]: r[1] for r in cur.fetchall()}

    cur.execute("""
        SELECT invoice_number, sku_code, sku_name, category, quantity, unit_price, line_total
        FROM tz_sales_invoices WHERE company_id = %s
    """, (company_id,))
    lines = []
    for r in cur.fetchall():
        inv, sku = r[0], r[1]
        if not inv or inv not in id_of:
            log_issue(cur, company_id, SOURCE,
                      Unmapped("sales_invoice_line", "invoice_number", "orphan_reference", inv))
            continue
        ref = stable_row_id(inv, sku, num(r[4]), num(r[5]), num(r[6]))
        lines.append({
            "source_ref": ref, "raw": None, "invoice_id": id_of[inv],
            "invoice_number": inv, "sku": sku, "sku_name": r[2], "category": r[3],
            "quantity": float(r[4] or 0), "unit_price": float(r[5] or 0),
            "line_total": float(r[6] or 0),
        })
    n_line = _upsert(cur, "canon_sales_invoice_line", company_id, lines)
    return n_head, n_line


def _rebuild_inventory(cur, company_id: str) -> int:
    cur.execute("""
        SELECT sku_code, sku_name, category, warehouse, quantity, unit_cost, total_value,
               is_raw_material, is_negative_stock
        FROM tz_inventory_valuation WHERE company_id = %s
    """, (company_id,))
    rows = []
    for r in cur.fetchall():
        if not r[0]:
            log_issue(cur, company_id, SOURCE,
                      Unmapped("inventory_item", "sku_code", "missing_required", None))
            continue
        ref = stable_row_id(r[0], r[3])  # sku + warehouse
        rows.append({
            "source_ref": ref, "confidence": 1.0, "raw": None,
            "sku": r[0], "sku_name": r[1], "category": r[2], "warehouse": r[3],
            "quantity": float(r[4] or 0), "qty_reserved": None,
            "unit_cost": float(r[5] or 0), "total_value": float(r[6] or 0),
            "is_raw_material": bool(r[7]), "is_negative_stock": bool(r[8]),
            "last_movement_date": None,
        })
    return _upsert(cur, "canon_inventory_item", company_id, rows)


def _rebuild_payments(cur, company_id: str) -> int:
    # AR/receivables position from the tz_ar_aging snapshot.
    cur.execute("""
        SELECT customer_name, customer_code, invoice_number, invoice_date, due_date,
               invoice_amount, outstanding_amount, days_overdue, aging_bucket
        FROM tz_ar_aging WHERE company_id = %s
    """, (company_id,))
    rows = []
    for r in cur.fetchall():
        if not r[2] and not r[0]:
            log_issue(cur, company_id, SOURCE,
                      Unmapped("payment", "invoice_number", "missing_identity", None))
            continue
        ref = stable_row_id(r[2], r[0])  # invoice_number + customer
        outstanding = float(r[6] or 0)
        rows.append({
            "source_ref": ref, "confidence": 1.0, "raw": None,
            "customer_ref": r[1], "customer_name": r[0],
            "invoice_number": r[2], "invoice_date": r[3], "due_date": r[4],
            "invoice_amount": float(r[5] or 0), "outstanding_amount": outstanding,
            "days_overdue": int(r[7]) if r[7] is not None else None,
            "aging_bucket": r[8], "mode": None, "reconciled": outstanding == 0,
        })
    return _upsert(cur, "canon_payment", company_id, rows)


# ── public entry point ────────────────────────────────────────────────────────
def rebuild_canonical(conn, company_id: str) -> LoadStats:
    """Rebuild all Slice-1 canonical objects for one company from tz_* data.
    Runs in a single transaction; safe + idempotent."""
    stats = LoadStats()
    with conn.cursor() as cur:
        stats.upserted["customer"] = _rebuild_customers(cur, company_id)
        h, l = _rebuild_sales(cur, company_id)
        stats.upserted["sales_invoice"] = h
        stats.upserted["sales_invoice_line"] = l
        stats.upserted["inventory_item"] = _rebuild_inventory(cur, company_id)
        stats.upserted["payment"] = _rebuild_payments(cur, company_id)
        cur.execute("SELECT COUNT(*) FROM ingest_issues WHERE company_id = %s AND source = %s",
                    (company_id, SOURCE))
        stats.issues = int(cur.fetchone()[0] or 0)
    conn.commit()
    logger.info("canonical rebuilt for %s: %s (issues=%d)",
                company_id, stats.upserted, stats.issues)
    return stats


def _companies(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT DISTINCT company_id FROM tz_sales_invoices ORDER BY 1")
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
        # Clear this company's prior issues so the log reflects the latest run.
        with conn.cursor() as cur:
            cur.execute("DELETE FROM ingest_issues WHERE company_id = %s AND source = %s",
                        (cid, SOURCE))
        conn.commit()
        s = rebuild_canonical(conn, cid)
        print(f"{cid}: {s.upserted}  issues={s.issues}")
    conn.close()
