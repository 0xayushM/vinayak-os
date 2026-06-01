"""
scripts/dedup_tz_tables.py
───────────────────────────
One-time cleanup for the duplicate-row bug.

TranzAct returns a fresh `uuid` on every fetch, and the upsert keyed on
(company_id, raw_id). So each sync re-inserted every row under a new id,
producing 7×–32× duplicates and inflating every total/count on the dashboard.

The pipelines now derive `raw_id` from a deterministic hash of each record's
*immutable* natural key (see pipelines/helpers.stable_row_id). This script makes
the existing data consistent with that:

  1. For each table, keep ONE row per natural key (the most recently fetched),
     deleting the duplicates.
  2. Recompute every surviving row's raw_id with the SAME hash the pipelines now
     use, so the next sync updates rows in place instead of re-duplicating.

Idempotent: running it twice is a no-op. Wrapped in a single transaction.

Usage:  PYTHONPATH=. python3 vinayak/scripts/dedup_tz_tables.py [--commit]
        (without --commit it prints what it WOULD do and rolls back)
"""
from __future__ import annotations

import os
import sys

import psycopg2
import psycopg2.extras

from vinayak.pipelines.helpers import num, stable_row_id

# table → (natural-key columns in pipeline hash order, set of numeric key cols)
SPECS = {
    "tz_sales_invoices":     (["invoice_number", "sku_code", "quantity", "unit_price", "line_total"],
                              {"quantity", "unit_price", "line_total"}),
    "tz_purchase_invoices":  (["invoice_number", "item_code", "quantity", "unit_price", "line_total"],
                              {"quantity", "unit_price", "line_total"}),
    "tz_sales_orders":       (["order_number", "sku_code", "ordered_qty"], {"ordered_qty"}),
    "tz_purchase_orders":    (["po_number"], set()),
    "tz_process_details":    (["work_order_number", "sku_code", "process_name"], set()),
    "tz_process_routing":    (["sku_code", "process_name"], set()),
    "tz_grn_qir":            (["grn_number", "item_code", "received_qty"], {"received_qty"}),
    "tz_sales_quotations":   (["quote_number", "sku_code"], set()),
    "tz_inventory_valuation": (["sku_code", "warehouse"], set()),
    "tz_ar_aging":           (["invoice_number", "customer_name"], set()),
}


def _load_env(path: str = ".env") -> dict:
    env = {}
    for line in open(path):
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    return env


def main(commit: bool) -> None:
    env = _load_env()
    conn = psycopg2.connect(env["DATABASE_URL"])
    cur = conn.cursor()
    grand_before = grand_after = 0

    for table, (keys, _numeric) in SPECS.items():
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        before = cur.fetchone()[0]

        # 1. Keep the most-recently-fetched row per (company_id, *keys).
        partition = ", ".join(["company_id"] + keys)
        cur.execute(f"""
            DELETE FROM {table} t USING (
                SELECT ctid,
                       row_number() OVER (
                           PARTITION BY {partition}
                           ORDER BY fetched_at DESC NULLS LAST, ctid
                       ) AS rn
                FROM {table}
            ) d
            WHERE t.ctid = d.ctid AND d.rn > 1
        """)

        # 2. Recompute raw_id on survivors to match the new hashing.
        cur.execute(f"SELECT ctid, {', '.join(keys)} FROM {table}")
        updates = []
        for r in cur.fetchall():
            ctid = r[0]
            parts = [num(v) if k in _numeric else v for k, v in zip(keys, r[1:])]
            updates.append((stable_row_id(*parts), ctid))
        psycopg2.extras.execute_batch(
            cur, f"UPDATE {table} SET raw_id = %s WHERE ctid = %s", updates, page_size=500)

        cur.execute(f"SELECT COUNT(*), COUNT(DISTINCT raw_id) FROM {table}")
        after, distinct_id = cur.fetchone()
        grand_before += before
        grand_after += after
        flag = "  ⚠ raw_id NOT unique!" if distinct_id != after else ""
        print(f"{table:26s} {before:6d} → {after:6d}  (distinct raw_id={distinct_id}){flag}")

    print(f"{'TOTAL':26s} {grand_before:6d} → {grand_after:6d}")
    if commit:
        conn.commit()
        print("COMMITTED.")
    else:
        conn.rollback()
        print("DRY RUN — rolled back. Re-run with --commit to apply.")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main(commit="--commit" in sys.argv)
