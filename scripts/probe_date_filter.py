"""
scripts/probe_date_filter.py
─────────────────────────────
Find the date-filter shape TranzAct's /generate_report actually honours for
report 29 (Sales Invoices).

Why this is needed: the column metadata shows the date column's API name is
"documentDate" (camelCase), and our current filter sends
{"filters": {"from_date", "to_date"}} — which references no real column, so the
server ignores it and returns the whole report every sync.

Method (decisive, not a guess):
  • Baseline: fetch page 1 with NO filter → note total_items and the newest date.
  • Probe window: 2026-02-01 → 2026-04-30 (we KNOW this brand has Feb–Apr data,
    and the window EXCLUDES the newest May/Jun rows).
  • For each candidate filter shape, fetch page 1 and check:
        – did total_items drop below the baseline?  AND/OR
        – is the newest returned row on/before 2026-04-30?
    Either proves the filter was applied. A shape that returns the full
    baseline (newest row = mid-June) was ignored.
  • Only page 1 is fetched per variant (no pagination) to stay light on the
    rate limit. A clear WINNER is printed at the end.

Run with the project venv from the repo root:
    ./venv/bin/python scripts/probe_date_filter.py [company_id]

Read-only against TranzAct; writes ./out/probe_results.json.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import requests

from vinayak.config import DATABASE_URL, TRANZACT_BASE_URL, TRANZACT_REPORTING_URL
from vinayak.adapters.tranzact.auth import get_access_token

REPORT_ID = "29"
COMPANY = sys.argv[1] if len(sys.argv) > 1 else "kbrushes"
SLEEP = 8.0  # seconds between requests — stay under the rate limit

# Probe window: known to contain data, and ends well before the newest rows.
F_DT = datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc)
T_DT = datetime(2026, 4, 30, 23, 59, 59, tzinfo=timezone.utc)
TO_DATE = T_DT.date()

ISO_F, ISO_T = F_DT.date().isoformat(), T_DT.date().isoformat()
DMY_F, DMY_T = F_DT.strftime("%d/%m/%Y"), T_DT.strftime("%d/%m/%Y")
MS_F, MS_T = int(F_DT.timestamp() * 1000), int(T_DT.timestamp() * 1000)

OUT = Path(__file__).resolve().parent.parent / "out"
OUT.mkdir(exist_ok=True)


def load_creds(company_id: str):
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
    return _decrypt(row[0])


def newest_date(rows: list[dict]):
    ds = []
    for r in rows:
        v = r.get("document_date")
        if isinstance(v, (int, float)) and v:
            ds.append(datetime.fromtimestamp(v / 1000, tz=timezone.utc).date())
    return max(ds) if ds else None


# Candidate filter payloads. We try the column's real API name "documentDate"
# (and a few generic shapes) across epoch-ms / ISO / DD-MM-YYYY value formats.
def variants() -> list[tuple[str, dict]]:
    return [
        ("CURRENT nested from_date/to_date ISO", {"filters": {"from_date": ISO_F, "to_date": ISO_T}}),
        ("nested from_date/to_date epoch-ms", {"filters": {"from_date": MS_F, "to_date": MS_T}}),
        ("nested from_date/to_date DD/MM/YYYY", {"filters": {"from_date": DMY_F, "to_date": DMY_T}}),
        ("documentDate {from,to} ISO", {"filters": {"documentDate": {"from": ISO_F, "to": ISO_T}}}),
        ("documentDate {from,to} epoch-ms", {"filters": {"documentDate": {"from": MS_F, "to": MS_T}}}),
        ("documentDate {start,end} epoch-ms", {"filters": {"documentDate": {"start": MS_F, "end": MS_T}}}),
        ("documentDate [from,to] epoch-ms", {"filters": {"documentDate": [MS_F, MS_T]}}),
        ("documentDate {min,max} epoch-ms", {"filters": {"documentDate": {"min": MS_F, "max": MS_T}}}),
        ("filters[] key/type/value date_range ms",
         {"filters": [{"key": "documentDate", "type": "date_range", "value": [MS_F, MS_T]}]}),
        ("filters[] column/operator between ms",
         {"filters": [{"column": "documentDate", "operator": "between", "value": [MS_F, MS_T]}]}),
        ("filters[] field/from/to ISO",
         {"filters": [{"field": "documentDate", "from": ISO_F, "to": ISO_T}]}),
        ("date_range top-level column ms",
         {"date_range": {"column": "documentDate", "from": MS_F, "to": MS_T}}),
        ("documentDate {$gte,$lte} epoch-ms",
         {"filters": {"documentDate": {"$gte": MS_F, "$lte": MS_T}}}),
        ("snake document_date {from,to} ISO", {"filters": {"document_date": {"from": ISO_F, "to": ISO_T}}}),
        ("top-level from_date/to_date ISO", {"from_date": ISO_F, "to_date": ISO_T}),
    ]


def main() -> None:
    creds = load_creds(COMPANY)
    token = get_access_token(base_url=TRANZACT_BASE_URL,
                            email=creds["email"], password=creds["password"])
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{TRANZACT_REPORTING_URL}/generate_report"

    def fetch(filt: dict):
        payload = {"report": {"id": REPORT_ID}, "pagination": {"page": 1, "per_page": 50}}
        payload.update(filt)
        r = requests.post(url, headers=headers, json=payload, timeout=90)
        try:
            body = r.json()
        except Exception:
            return r.status_code, None, []
        data = body.get("data", {}) if isinstance(body, dict) else {}
        return r.status_code, data.get("total_items"), data.get("results", [])

    print(f"Company: {COMPANY}   Probe window: {ISO_F} → {ISO_T}")
    print("Fetching baseline (no filter)…")
    _, base_total, base_rows = fetch({})
    base_newest = newest_date(base_rows)
    print(f"  baseline total_items={base_total}  newest row={base_newest}\n")
    time.sleep(SLEEP)

    results = []
    print(f"{'variant':<44}{'HTTP':>5}{'total':>7}{'newest':>13}  verdict")
    print("─" * 96)
    for label, filt in variants():
        try:
            status, total, rows = fetch(filt)
            nd = newest_date(rows)
            narrowed = (
                (isinstance(total, int) and isinstance(base_total, int) and total < base_total)
                or (nd is not None and nd <= TO_DATE)
            )
            verdict = "✅ NARROWED" if narrowed else "ignored"
            print(f"{label:<44}{status:>5}{str(total):>7}{str(nd):>13}  {verdict}")
            results.append({"variant": label, "filter": filt, "http": status,
                            "total_items": total, "newest": str(nd), "narrowed": narrowed})
        except Exception as exc:  # noqa: BLE001
            print(f"{label:<44}{'ERR':>5}{'':>7}{'':>13}  {exc}")
            results.append({"variant": label, "filter": filt, "error": str(exc)})
        time.sleep(SLEEP)

    (OUT / "probe_results.json").write_text(json.dumps(
        {"company": COMPANY, "window": [ISO_F, ISO_T],
         "baseline_total": base_total, "baseline_newest": str(base_newest),
         "results": results}, indent=2, default=str))

    winners = [r for r in results if r.get("narrowed")]
    print("\n" + "═" * 96)
    if winners:
        print("WINNER(S) — these filter shapes are honoured:")
        for w in winners:
            print(f"  • {w['variant']}")
            print(f"    payload: {json.dumps(w['filter'])}")
        print("\nTell me which one and I'll wire it into reports.py + the pipelines.")
    else:
        print("No variant narrowed the result — report 29 may not accept a server-side")
        print("date filter at all (the UI likely filters client-side). In that case we")
        print("keep full-fetch but add client-side incremental trimming. Send me out/probe_results.json.")
    print(f"\nSaved: {OUT / 'probe_results.json'}")


if __name__ == "__main__":
    main()
