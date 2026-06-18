"""
scripts/dump_report29.py
─────────────────────────
Pull the RAW TranzAct response for Sales Invoices (report 29) and write it out
so we can see exactly what the API returns — including total_items, the
pagination behaviour, and every row.

It pages explicitly (does NOT trust our client's stop condition) so we can see
whether the API caps a page at 100 rows and/or misreports total_items — which
is why the sync only ever sees ~13 May onward.

Outputs (under ./out/):
  • report29_raw.json   — complete raw response: every page body + merged rows
  • report29_response.html — readable report; open it and Print → Save as PDF

Run with the project venv from the repo root:
    ./venv/bin/python scripts/dump_report29.py            # company kbrushes, no date filter
    ./venv/bin/python scripts/dump_report29.py kbrushes 2026-03-01 2026-06-17

Read-only against TranzAct; writes only local files under ./out/.
"""
from __future__ import annotations

import html
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import requests

from vinayak.config import DATABASE_URL, TRANZACT_BASE_URL, TRANZACT_REPORTING_URL
from vinayak.adapters.tranzact.auth import get_access_token

REPORT_ID = "29"
COMPANY = sys.argv[1] if len(sys.argv) > 1 else "kbrushes"
FROM = sys.argv[2] if len(sys.argv) > 2 else None
TO = sys.argv[3] if len(sys.argv) > 3 else None
PER_PAGE = 200
MAX_PAGES = 30  # safety cap; we keep paging while rows keep coming

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


def d(ms):
    if isinstance(ms, (int, float)) and ms:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()
    return None


def main() -> None:
    creds = load_creds(COMPANY)
    token = get_access_token(base_url=TRANZACT_BASE_URL,
                            email=creds["email"], password=creds["password"])
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    url = f"{TRANZACT_REPORTING_URL}/generate_report"

    filt = {"filters": {"from_date": FROM, "to_date": TO}} if (FROM or TO) else {}

    pages, merged = [], []
    page = 1
    with requests.Session() as s:
        while page <= MAX_PAGES:
            payload = {"report": {"id": REPORT_ID},
                       "pagination": {"page": page, "per_page": PER_PAGE}}
            payload.update(filt)
            r = s.post(url, headers=headers, json=payload, timeout=90)
            body = r.json()
            data = body.get("data", {}) if isinstance(body, dict) else {}
            results = data.get("results", []) if isinstance(data, dict) else []
            total_items = data.get("total_items")
            pages.append({
                "page": page, "per_page_sent": PER_PAGE,
                "http_status": r.status_code,
                "results_returned": len(results),
                "total_items_field": total_items,
            })
            merged.extend(results)
            print(f"page {page}: returned {len(results)} rows  (total_items={total_items})")
            if not results:
                break
            # Keep going while the API hands back a full-ish page; stop when it
            # clearly returned the last partial/empty page.
            if len(results) < (total_items or 0) and len(merged) < (total_items or 0):
                page += 1
                continue
            break

    dates = [x for x in (d(r.get("document_date")) for r in merged) if x]
    invoices = sorted({r.get("document_no_text") for r in merged if r.get("document_no_text")})
    span = f"{min(dates)} → {max(dates)}" if dates else "no dated rows"

    # ── Save complete raw payload ────────────────────────────────────────────
    raw_path = OUT / "report29_raw.json"
    raw_path.write_text(json.dumps(
        {"company": COMPANY, "filter": filt or "none",
         "fetched_at": datetime.now(timezone.utc).isoformat(),
         "page_log": pages, "merged_rows": merged}, indent=2, default=str))

    # ── Build readable HTML (print to PDF) ───────────────────────────────────
    cols = ["document_no_text", "document_date", "customer_name", "item_name",
            "quantity", "item_price", "item_total_value", "tax", "grand_total"]
    def cell(r, k):
        v = r.get(k)
        if k == "document_date":
            v = d(v) or v
        return html.escape("" if v is None else str(v))

    rows_html = "\n".join(
        "<tr>" + "".join(f"<td>{cell(r, k)}</td>" for k in cols) + "</tr>"
        for r in merged
    )
    page_rows = "\n".join(
        f"<tr><td>{p['page']}</td><td>{p['per_page_sent']}</td>"
        f"<td>{p['http_status']}</td><td>{p['results_returned']}</td>"
        f"<td>{p['total_items_field']}</td></tr>" for p in pages
    )
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    htmldoc = f"""<!doctype html><html><head><meta charset="utf-8">
<title>TranzAct report 29 — {html.escape(COMPANY)}</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Arial,sans-serif;margin:24px;color:#111}}
 h1{{font-size:18px}} h2{{font-size:14px;margin-top:22px}}
 table{{border-collapse:collapse;width:100%;font-size:11px;margin-top:8px}}
 th,td{{border:1px solid #ccc;padding:4px 6px;text-align:left}}
 th{{background:#f3f3f3}} .meta td{{border:none;padding:2px 8px}}
 tr:nth-child(even){{background:#fafafa}}
</style></head><body>
<h1>TranzAct — Report 29 (Sales Invoices) — {html.escape(COMPANY)}</h1>
<table class="meta">
 <tr><td><b>Fetched</b></td><td>{datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}</td></tr>
 <tr><td><b>Filter sent</b></td><td>{html.escape(json.dumps(filt) if filt else "none")}</td></tr>
 <tr><td><b>Line-items fetched</b></td><td>{len(merged)}</td></tr>
 <tr><td><b>Distinct invoices</b></td><td>{len(invoices)}</td></tr>
 <tr><td><b>Date span</b></td><td>{span}</td></tr>
</table>
<h2>Pagination (what the API actually did)</h2>
<table><tr><th>page</th><th>per_page sent</th><th>HTTP</th><th>rows returned</th><th>total_items field</th></tr>
{page_rows}</table>
<h2>All rows returned ({len(merged)})</h2>
<table><tr>{head}</tr>
{rows_html}</table>
</body></html>"""
    html_path = OUT / "report29_response.html"
    html_path.write_text(htmldoc)

    print(f"\nLine-items: {len(merged)}   invoices: {len(invoices)}   span: {span}")
    print(f"Raw JSON : {raw_path}")
    print(f"HTML     : {html_path}")
    print("Open the HTML and use your browser's Print → Save as PDF.")


if __name__ == "__main__":
    main()
