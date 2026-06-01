# Dashboard Calculations — Full Reference & Bug Review

Every metric the dashboard shows, the exact formula behind it (from
`vinayak/schema/queries.py`), and the discrepancies I found while tracing them.
Read the **"Bugs found"** section first — two of them almost certainly explain why
your numbers don't match the source data.

---

## ⚠️ Bugs found (read this first)

### BUG 1 — Revenue & spend are multiplied by the number of line items (the big one)

`tz_sales_invoices` and `tz_purchase_invoices` are **line-level** tables: one row
per invoice *line* (each row has `sku_code`, `quantity`, `line_total`), and every
line of the same invoice repeats the same header `invoice_total`.

Several KPIs do `SUM(invoice_total)` across those line rows. So an invoice with 5
line items has its total counted **5 times**. Revenue is overstated by roughly the
average number of lines per invoice.

Affected functions (all use `SUM(invoice_total)` over line rows):

- `get_revenue_summary` — `period_total`, `ytd_total`
- `_sales_monthly_avg` — `monthly_avg`
- `get_revenue_trend` — every month's `revenue`
- `get_revenue_daily` — every day's `revenue`
- `get_customer_concentration` — every slice + total
- `get_top_customers_revenue` — `revenue`, `pct_of_total`
- `get_purchases_summary` — `period_spend`
- `_purchase_monthly_avg` — `monthly_avg`
- `get_top_vendors_spend` — `spend`, `pct_of_total`

**Proof it's wrong by internal contradiction:** `get_top_skus_revenue` and the
invoice detail-list footer correctly use `SUM(line_total)`. So SKU revenue and the
revenue-summary number are computed on two different bases and can *never*
reconcile. The summary will always be larger.

**The fix** is one of:
- `SUM(line_total)` — the true sum of goods sold (excludes tax/freight if those
  live only in `invoice_total`), **or**
- aggregate to the invoice first: `SUM(invoice_total)` over a
  `SELECT DISTINCT invoice_number, invoice_total` subquery (keeps tax/freight).

Pick based on whether `invoice_total` includes tax. If "revenue" should mean the
taxable goods value, use `line_total`. If it should match the printed invoice grand
total, use the distinct-invoice approach. **They must all use the same basis.**

Quick check to size the error:
```sql
SELECT
  SUM(line_total)                                   AS line_basis,
  (SELECT SUM(invoice_total)
     FROM (SELECT DISTINCT invoice_number, invoice_total
             FROM tz_sales_invoices WHERE company_id = %s) d) AS invoice_basis,
  SUM(invoice_total)                                AS current_buggy_basis
FROM tz_sales_invoices WHERE company_id = %s;
```
`current_buggy_basis` is what the dashboard shows today. It should match one of the
other two; the gap is the over-count.

---

### BUG 2 — "Latest data" panels and "last N days from today" panels disagree

Two different windowing rules are mixed across the codebase:

- **Anchored to latest available data** (via `_resolve_window`): revenue summary,
  revenue trend, revenue daily, concentration, top customers, top SKUs. These find
  your newest invoice date and look back from *there*, so they're never empty.
- **Anchored to today** (`date.today() - period_days`): `get_purchases_summary`,
  `get_top_vendors_spend`, `get_production_summary`, `get_quote_summary`,
  `get_grn_summary`. These look back from *today*.

If the brand's most recent sync data is, say, six weeks old, the revenue panels
show a healthy "last 30 days" (anchored to that data) while purchases / production
/ quotes / GRN show **₹0 or near-zero** for the "same" last 30 days — because
nothing falls in the last 30 days *from today*. That's a guaranteed mismatch the
moment data isn't perfectly current.

**The fix:** route the purchase/production/quote/GRN summaries through
`_resolve_window` too (anchor to latest data), so every panel uses one rule.

---

### BUG 3 — Order / PO status filters use exact lowercase strings

`get_order_book_summary`, `get_overdue_orders`, `get_open_pos`, `get_overdue_pos`,
and `get_purchases_summary` filter with exact matches like
`status NOT IN ('dispatched','cancelled')` / `status = 'dispatched'`.

But `get_production_summary` explicitly documents that TranzAct returns
**mixed-case** status text (`'WIP'`, `'Pending'`, `'Planned'`) and there is no
literal lowercase `'completed'`. If sales-order / PO statuses are likewise
`'Dispatched'`, `'Cancelled'`, `'Received'`, then:

- `status = 'dispatched'` never matches → `dispatched_pct` reads 0%.
- `status NOT IN ('dispatched','cancelled')` matches *everything* → open counts and
  open values are overstated (cancelled/dispatched orders counted as open).

**The fix:** use `ILIKE` / case-insensitive comparison consistently, the same way
production already does. First confirm the real values:
```sql
SELECT DISTINCT status FROM tz_sales_orders   WHERE company_id = %s;
SELECT DISTINCT status FROM tz_purchase_orders WHERE company_id = %s;
```

---

## ✅ Company isolation (the "merged data" question)

**At the query layer, there is no merge risk.** Every single function filters
`WHERE company_id = %s` as its first predicate (verified across all ~30 functions,
including the generic `_paged_list` builder and the date/sync helpers). Two brands
in the same tables cannot read each other's rows.

So if two brands ever showed *identical* numbers, the cause is upstream of these
queries, one of:

1. **Same data written under the same `company_id`** — the sync wrote both brands'
   data to one tenant key. Check:
   ```sql
   SELECT company_id, COUNT(*), MIN(invoice_date), MAX(invoice_date)
   FROM tz_sales_invoices GROUP BY company_id;
   ```
   You should see one row per brand with different counts. If a brand is missing or
   two brands collapsed into one key, that's the leak.

2. **Same TranzAct credentials** saved for both brands — then the data really *is*
   identical and the dashboard is right. Confirm each brand's saved TranzAct email
   differs.

3. **Frontend cache** (the issue fixed earlier — SWR url-keyed cache + missing
   `Vary` header). Already addressed with the workspace-scoping SWR middleware and
   `Cache-Control: no-store` + `Vary: X-Workspace-Id`. A hard refresh of both tabs
   clears any stale pre-fix cache.

---

## Full calculation reference

### Sales / revenue

**`get_revenue_summary`** (Revenue KPIs)
- `period_total` = `SUM(invoice_total)` over window  ⚠️ BUG 1
- `invoice_count` = `COUNT(DISTINCT invoice_number)` ✓
- `customer_count` = `COUNT(DISTINCT customer_code)` ✓
- `avg_invoice_value` = `period_total / invoice_count` (inherits BUG 1)
- `monthly_avg` = trailing-12-month `SUM(invoice_total)` ÷ distinct months with data ⚠️ BUG 1
- `ytd_total` = `SUM(invoice_total)` where year = latest-data year ⚠️ BUG 1
- Window anchored to latest invoice date (BUG 2 side: this one anchors to data)

**`get_revenue_trend`** — monthly `SUM(invoice_total)` + `COUNT(DISTINCT invoice_number)`, gap-filled to a continuous month axis. ⚠️ BUG 1 on revenue.

**`get_revenue_daily`** — daily `SUM(invoice_total)` + distinct invoice count, gap-filled, capped ~400 points. ⚠️ BUG 1.

**`get_customer_concentration`** — top-5 customers by `SUM(invoice_total)` + an "Others" slice = `total − top5`. ⚠️ BUG 1 (slices and total inflated equally, so *shares* are roughly right but absolute ₹ are not).

**`get_top_customers_revenue`** — per customer `SUM(invoice_total)`, `COUNT(DISTINCT invoice_number)`, and `pct = 100 × customer_total / grand_total`. Top 15. ⚠️ BUG 1.

**`get_top_skus_revenue`** — per SKU `SUM(line_total)` ✓ (correct basis), `SUM(quantity)`, distinct invoice count. Top 20.

### Inventory (snapshot — no date window)

**`get_inventory_summary`** — `SUM(total_value)`, `COUNT(DISTINCT sku_code)`,
`COUNT(*) FILTER (quantity < 0)` as negative-stock, `COUNT(DISTINCT warehouse)`. ✓

**`get_inventory_by_category`** — per category `SUM(total_value)` + distinct SKU
count, top 15 by value. ✓

**`get_top_stock_holdings`** — highest `total_value` SKUs where `quantity > 0`, top 20. ✓

### Purchases

**`get_purchases_summary`** — `period_spend = SUM(invoice_total)` ⚠️ BUG 1, window
anchored to **today** ⚠️ BUG 2; `monthly_avg` trailing-12mo ⚠️ BUG 1;
`vendor_count`, `invoice_count` distinct ✓; `overdue_po_count` = POs past
`expected_date` not received/cancelled ⚠️ BUG 3 (status case).

**`get_top_vendors_spend`** — per vendor `SUM(invoice_total)` + pct of total, top
10, window anchored to today. ⚠️ BUG 1, ⚠️ BUG 2.

### Production

**`get_production_summary`** — `fg_produced = SUM(produced_qty)`,
`rejected = SUM(rejected_qty)`, `reject_rate = 100 × rejected / (produced+rejected)`,
`wip_count` = distinct work orders where `status ILIKE 'wip'`, `completed_count` =
distinct work orders completed/closed *or* `produced ≥ planned`. Window anchored to
**today** ⚠️ BUG 2. (Status handled case-insensitively here — good.)

**`get_production_wip`** — status breakdown counts + planned/produced sums; recent
WIP work-order list (top 30 by date). ✓

### Quotations & GRN

**`get_quote_summary`** — won = `converted_to_order OR status ILIKE 'won'/'accepted'`;
open = not won/lost/rejected/cancelled; `conversion_rate = won / total`. Window
anchored to **today** ⚠️ BUG 2.

**`get_grn_summary`** — `received_count` distinct GRNs, `rejection_rate =
SUM(rejected_qty) / SUM(received_qty)`, `pending_qir = COUNT(*) where rejected_qty
IS NULL`. `total_value` is hard-coded 0 (source report 34 has no money). Window
anchored to **today** ⚠️ BUG 2.

**`get_bom_coverage`** — `coverage = distinct manufactured SKUs with a routing /
distinct manufactured SKUs`. ✓

### Orders & AR (operational)

**`get_order_book_summary`** — open = `status NOT IN ('dispatched','cancelled')`
⚠️ BUG 3; `dispatched_pct = 100 × dispatched / total` ⚠️ BUG 3; overdue = past
`delivery_date` and still open.

**`get_ar_summary`** — aging buckets `SUM(outstanding_amount)` + counts; `overdue_*`
filtered by `days_overdue > 0`; top-15 exposures by outstanding. ✓ (AR is a
pre-aggregated snapshot table, so no line-multiplication risk.)

**`get_ar_customer_exposure`** — per customer outstanding, invoice count, max
days-overdue, overdue value. Top 15. ✓

**`get_overdue_pos` / `get_overdue_orders`** — past expected/delivery date and not
received/dispatched/cancelled; totals + top-25 list. ⚠️ BUG 3 (status case).

**`get_open_pos`** — open = not received/cancelled; overdue = open subset past
`expected_date`; by-vendor top 10. ⚠️ BUG 3 (status case).

### Detail lists (paginated tables)

`get_sales_invoices_list`, `get_purchase_invoices_list`, `get_sales_orders_list`,
`get_purchase_orders_list`, `get_production_list`, `get_inventory_list`,
`get_ar_invoices_list`, and the generic `_paged_list`:
- `total_count = COUNT(*)` (row count — this is the footer "of N"; correct after the
  earlier fix).
- `filtered_total = SUM(<money col>)` — note this is a **line-level sum**
  (`line_total` / `order_value` / `po_value` / `total_value`). It's *not* shown as
  the footer count anymore, but if you ever surface it as "total value," it's the
  correct line-level basis (unlike BUG 1's header sum).
- Date window defaults to the **full data span** when no range is given (these
  correctly anchor to data, not today).

---

## Suggested fix order

1. **BUG 1** (revenue/spend over-count) — highest impact, makes every headline ₹
   wrong. Decide the basis (`line_total` vs distinct-invoice) and apply it
   everywhere consistently.
2. **BUG 2** (today vs latest-data window) — route the 5 today-anchored summaries
   through `_resolve_window`.
3. **BUG 3** (status case) — confirm actual status strings, switch to `ILIKE`.
4. Run the company-isolation SQL checks above to confirm no upstream merge.
