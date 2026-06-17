"""Read-only cross-check of daily revenue: goods (SUM line_total) vs invoiced (per-invoice net)."""
import psycopg2
from vinayak.config import DATABASE_URL

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# Pick the company with the most invoice lines.
cur.execute("""
    SELECT company_id, COUNT(*) FROM canon_sales_invoice_flat GROUP BY 1 ORDER BY 2 DESC LIMIT 1
""")
company_id, _ = cur.fetchone()
print("company_id:", company_id)

# Anchor window = last 14 days of available data.
cur.execute("SELECT MAX(invoice_date) FROM canon_sales_invoice_flat WHERE company_id=%s", (company_id,))
data_to = cur.fetchone()[0]
print("data_to:", data_to)

# A) What the API does today: SUM(line_total) per day (goods, ex-tax).
cur.execute("""
    SELECT invoice_date, COALESCE(SUM(line_total),0)
    FROM canon_sales_invoice_flat
    WHERE company_id=%s AND invoice_date > %s - INTERVAL '14 days' AND invoice_date <= %s
    GROUP BY invoice_date ORDER BY invoice_date
""", (company_id, data_to, data_to))
api_daily = {r[0]: float(r[1]) for r in cur.fetchall()}

# B) Per-invoice printed net total per day (incl tax/freight) — the "original".
cur.execute("""
    SELECT invoice_date, COALESCE(SUM(inv_net),0) FROM (
        SELECT invoice_date, invoice_number, MAX(invoice_total) AS inv_net
        FROM canon_sales_invoice_flat
        WHERE company_id=%s AND invoice_date > %s - INTERVAL '14 days' AND invoice_date <= %s
        GROUP BY invoice_date, invoice_number
    ) d GROUP BY invoice_date ORDER BY invoice_date
""", (company_id, data_to, data_to))
invoiced_daily = {r[0]: float(r[1]) for r in cur.fetchall()}

# C) Naive SUM(invoice_total) over flat rows (the fan-out trap) per day.
cur.execute("""
    SELECT invoice_date, COALESCE(SUM(invoice_total),0)
    FROM canon_sales_invoice_flat
    WHERE company_id=%s AND invoice_date > %s - INTERVAL '14 days' AND invoice_date <= %s
    GROUP BY invoice_date ORDER BY invoice_date
""", (company_id, data_to, data_to))
fanout_daily = {r[0]: float(r[1]) for r in cur.fetchall()}

print(f"\n{'date':<12}{'A goods(API)':>16}{'B invoiced':>16}{'C fanout':>16}")
for d in sorted(api_daily):
    print(f"{str(d):<12}{api_daily[d]:>16,.0f}{invoiced_daily.get(d,0):>16,.0f}{fanout_daily.get(d,0):>16,.0f}")

ta, tb, tc = sum(api_daily.values()), sum(invoiced_daily.values()), sum(fanout_daily.values())
print(f"\n{'TOTAL':<12}{ta:>16,.0f}{tb:>16,.0f}{tc:>16,.0f}")
print(f"\nA (goods, what API returns) vs B (invoiced/printed): diff = {tb-ta:,.0f}  ({(tb-ta)/tb*100 if tb else 0:.1f}% of invoiced)")

# D) RAW source: SUM(line_total) per day directly from tz_sales_invoices (the "original").
cur.execute("""
    SELECT invoice_date, COALESCE(SUM(line_total),0)
    FROM tz_sales_invoices
    WHERE company_id=%s AND invoice_date > %s - INTERVAL '14 days' AND invoice_date <= %s
    GROUP BY invoice_date ORDER BY invoice_date
""", (company_id, data_to, data_to))
raw_daily = {r[0]: float(r[1]) for r in cur.fetchall()}

print(f"\n--- CANON (API) vs RAW tz_sales_invoices (goods basis) ---")
print(f"{'date':<12}{'A canon':>16}{'D raw':>16}{'missing':>16}")
for d in sorted(set(api_daily) | set(raw_daily)):
    a, dd = api_daily.get(d, 0), raw_daily.get(d, 0)
    flag = "  <-- MISMATCH" if abs(a - dd) > 1 else ""
    print(f"{str(d):<12}{a:>16,.0f}{dd:>16,.0f}{dd-a:>16,.0f}{flag}")
td = sum(raw_daily.values())
print(f"\n{'TOTAL':<12}{ta:>16,.0f}{td:>16,.0f}{td-ta:>16,.0f}")
print(f"\nCanon vs raw: diff = {td-ta:,.0f}  ({(td-ta)/td*100 if td else 0:.2f}% dropped by canonical layer)")

# How many raw lines collapse under the stable_row_id dedup key?
cur.execute("""
    SELECT COUNT(*) AS raw_lines,
           COUNT(*) - COUNT(DISTINCT (invoice_number, sku_code, quantity, unit_price, line_total)) AS collapsed
    FROM tz_sales_invoices WHERE company_id=%s
""", (company_id,))
raw_lines, collapsed = cur.fetchone()
print(f"\nRaw lines: {raw_lines:,}   collapsed by (inv,sku,qty,price,total) dedup: {collapsed:,}")
conn.close()
