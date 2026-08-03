"""
scripts/smoke_test.py
──────────────────────
Run all 9 fixed pipelines over a 90-day window and print upserted row counts.
Verifies that data actually lands in Supabase.

Usage:
    python -m vinayak.scripts.smoke_test
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
load_dotenv()

from vinayak.pipelines.sales_invoices import SalesInvoicesPipeline
from vinayak.pipelines.ar_aging import ARAgingPipeline
from vinayak.pipelines.sales_orders import SalesOrdersPipeline
from vinayak.pipelines.purchase_invoices import PurchaseInvoicesPipeline
from vinayak.pipelines.purchase_orders import PurchaseOrdersPipeline
from vinayak.pipelines.grn_qir import GRNQIRPipeline
from vinayak.pipelines.inventory_valuation import InventoryValuationPipeline
from vinayak.pipelines.process_routing import ProcessRoutingPipeline
from vinayak.pipelines.process_details import ProcessDetailsPipeline

PIPELINES = [
    ("Inventory Valuation", InventoryValuationPipeline),
    ("Process Routing",     ProcessRoutingPipeline),
    ("AR Aging",            ARAgingPipeline),
    ("Sales Invoices",      SalesInvoicesPipeline),
    ("Sales Orders",        SalesOrdersPipeline),
    ("Purchase Invoices",   PurchaseInvoicesPipeline),
    ("Purchase Orders",     PurchaseOrdersPipeline),
    ("GRN / QIR",           GRNQIRPipeline),
    ("Process Details",     ProcessDetailsPipeline),
]


def _creds_for(company_id: str):
    """Load and decrypt the stored TranzAct credentials for a workspace."""
    import psycopg2
    from vinayak.config import DATABASE_URL, TRANZACT_BASE_URL
    from vinayak.adapters.tranzact.client import TranzactCreds
    from vinayak.api.routes.connections import _decrypt

    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT encrypted_credentials FROM tool_connections
                   WHERE company_id = %s AND tool_name = 'tranzact' AND is_active = TRUE""",
                (company_id,),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        sys.exit(f"No active TranzAct connection for workspace '{company_id}'.")
    cred = _decrypt(row[0])
    return TranzactCreds(email=cred["email"], password=cred["password"],
                         base_url=TRANZACT_BASE_URL)


if len(sys.argv) < 2:
    sys.exit("Usage: python -m vinayak.scripts.smoke_test <company_id>   e.g. kbrushes")
COMPANY = sys.argv[1]
CREDS = _creds_for(COMPANY)

print(f"\n🚀  Smoke test for workspace '{COMPANY}' (newest 2 pages per report)\n")
total = 0
for label, PipelineCls in PIPELINES:
    try:
        res = PipelineCls().run_chunk(
            company_id=COMPANY, creds=CREDS, start_page=1, max_pages=2,
        )
        print(f"  ✅  {label:<25} fetched={res['rows_fetched']:>5}  upserted={res['rows_upserted']:>5}")
        total += res["rows_upserted"] or 0
    except Exception as exc:
        print(f"  ❌  {label:<25} FAILED: {exc}")

print(f"\n  Total rows upserted: {total}\n")
