"""
scripts/fetch_march.py
───────────────────────
Basic, direct check: pull Sales Invoices (report 29) from 1 Mar 2026 → today
straight from TranzAct, using the exact same client the sync uses.

It prints what the API actually returns so we can see whether (a) the data is
there and (b) our date filter is honoured.

Run with the project venv, from the repo root:
    source venv/bin/activate
    python scripts/fetch_march.py
or:
    ./venv/bin/python scripts/fetch_march.py [company_id]

Read-only — fetches reports, writes nothing.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import date, datetime

# Ensure the repo root (parent of this scripts/ dir) is importable, regardless
# of where the script is launched from.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2

from vinayak.config import DATABASE_URL, TRANZACT_BASE_URL
from vinayak.adapters.tranzact.client import TranzactCreds, fetch_report

REPORT_ID = "29"  # sales_invoices
COMPANY = sys.argv[1] if len(sys.argv) > 1 else "kbrushes"
FROM = "2026-03-01"
TO = date.today().isoformat()


def load_creds(company_id: str) -> TranzactCreds:
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
        raise SystemExit(f"No active TranzAct connection for '{company_id}'")
    c = _decrypt(row[0])
    return TranzactCreds(email=c["email"], password=c["password"], base_url=TRANZACT_BASE_URL)


def report(label: str, rows: list[dict]) -> None:
    dates = []
    for r in rows:
        v = r.get("document_date")
        if isinstance(v, (int, float)) and v:
            dates.append(datetime.utcfromtimestamp(v / 1000).date())
    invoices = {r.get("document_no_text") for r in rows if r.get("document_no_text")}
    span = f"{min(dates)} → {max(dates)}" if dates else "no dated rows"
    print(f"\n[{label}]")
    print(f"  line-items fetched : {len(rows)}")
    print(f"  distinct invoices  : {len(invoices)}")
    print(f"  date span          : {span}")


def main() -> None:
    creds = load_creds(COMPANY)
    print(f"Company: {COMPANY}   Report 29 (sales_invoices)")
    print(f"Asking TranzAct for: {FROM} → {TO}")

    # 1) Exactly what you asked: filtered Mar 1 → today (current filter shape).
    filtered = fetch_report(
        REPORT_ID,
        {"filters": {"from_date": FROM, "to_date": TO}},
        per_page=200, creds=creds,
    )
    report("FILTERED  from_date/to_date (what the sync sends)", filtered)

    # 2) Baseline: no filter at all — shows the true history the API holds.
    baseline = fetch_report(REPORT_ID, None, per_page=200, creds=creds)
    report("NO FILTER  (everything the API will give)", baseline)

    print("\nInterpretation:")
    print("  • If NO-FILTER reaches back to Mar/Apr but FILTERED does not →")
    print("    the date filter is the bug (wrong key/format); fix get_filters().")
    print("  • If NO-FILTER itself stops at mid-May → the API account only")
    print("    exposes recent data and history must be pulled another way.")


if __name__ == "__main__":
    main()
