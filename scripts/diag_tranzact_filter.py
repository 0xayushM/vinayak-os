"""
scripts/diag_tranzact_filter.py
────────────────────────────────
Decisive diagnostic for the "historical data not syncing" bug.

Symptom: tz_sales_invoices only holds the most recent ~30 days even though the
TranzAct API has the full history (report 29 reports 367 line-items back to
1 Apr). The backfill advances the watermark but stores no older rows — which
means the date-filter we send to /generate_report is not being honoured.

This script fetches report 29 (Sales Invoices) for an OLD window (April 2026)
using several candidate filter shapes and prints, for each, how many rows came
back and their actual date span. The variant whose span lands INSIDE the
requested window is the format TranzAct actually accepts. If every variant
returns the same recent rows as the no-filter baseline, the filter is being
ignored entirely.

Usage (from repo root, with .env / DB configured):
    python -m scripts.diag_tranzact_filter            # uses company 'kbrushes'
    python -m scripts.diag_tranzact_filter <company>  # another company

Read-only: it only issues GET-style report reads, writes nothing.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import psycopg2

from vinayak.config import DATABASE_URL, TRANZACT_BASE_URL
from vinayak.adapters.tranzact.client import TranzactCreds, fetch_report

REPORT_ID = "29"  # sales_invoices
COMPANY = sys.argv[1] if len(sys.argv) > 1 else "kbrushes"

# Old window we KNOW has data on the API side (per the raw invoice list).
WIN_FROM = datetime(2026, 4, 1, tzinfo=timezone.utc)
WIN_TO = datetime(2026, 4, 30, tzinfo=timezone.utc)


def _ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


def _load_creds(company_id: str) -> TranzactCreds:
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
        raise SystemExit(f"No active TranzAct connection for company '{company_id}'")
    c = _decrypt(row[0])
    return TranzactCreds(email=c["email"], password=c["password"], base_url=TRANZACT_BASE_URL)


def _span(rows: list[dict]) -> str:
    ds = []
    for r in rows:
        v = r.get("document_date")
        if isinstance(v, (int, float)) and v:
            ds.append(datetime.utcfromtimestamp(v / 1000).date())
    if not ds:
        return "no dated rows"
    return f"{min(ds)} → {max(ds)}"


# Candidate filter payloads for the April window. Order matters only for reading.
def _variants() -> list[tuple[str, dict]]:
    iso_f, iso_t = WIN_FROM.date().isoformat(), WIN_TO.date().isoformat()
    dmy_f, dmy_t = WIN_FROM.strftime("%d/%m/%Y"), WIN_TO.strftime("%d/%m/%Y")
    return [
        ("0. no filter (baseline)", {}),
        ("1. CURRENT: nested filters, ISO", {"filters": {"from_date": iso_f, "to_date": iso_t}}),
        ("2. nested filters, epoch-ms", {"filters": {"from_date": _ms(WIN_FROM), "to_date": _ms(WIN_TO)}}),
        ("3. nested filters, DD/MM/YYYY", {"filters": {"from_date": dmy_f, "to_date": dmy_t}}),
        ("4. top-level, ISO", {"from_date": iso_f, "to_date": iso_t}),
        ("5. nested filters, start_date/end_date ISO", {"filters": {"start_date": iso_f, "end_date": iso_t}}),
        ("6. nested filters, date_from/date_to ISO", {"filters": {"date_from": iso_f, "date_to": iso_t}}),
        ("7. nested filters, epoch-ms start/end", {"filters": {"start_date": _ms(WIN_FROM), "end_date": _ms(WIN_TO)}}),
    ]


def main() -> None:
    creds = _load_creds(COMPANY)
    print(f"Company: {COMPANY}   Report: {REPORT_ID} (sales_invoices)")
    print(f"Requested window: {WIN_FROM.date()} → {WIN_TO.date()}\n")
    print(f"{'variant':<46}{'rows':>7}   span")
    print("─" * 90)
    for label, filt in _variants():
        try:
            rows = fetch_report(REPORT_ID, filt or None, per_page=200, creds=creds)
            print(f"{label:<46}{len(rows):>7}   {_span(rows)}")
        except Exception as exc:  # noqa: BLE001
            print(f"{label:<46}{'ERR':>7}   {exc}")
    print("\nHow to read this:")
    print("  • A variant whose span is INSIDE Apr 2026 → that is the filter format to adopt.")
    print("  • If every variant matches the no-filter baseline (same recent span) → the")
    print("    server ignores our filter shape entirely; pick the variant that narrows it.")
    print("  • Whatever wins, set it in vinayak/adapters/tranzact/reports.py:get_filters()")
    print("    and the per-pipeline _get_filters() (sales_invoices.py et al.).")


if __name__ == "__main__":
    main()
