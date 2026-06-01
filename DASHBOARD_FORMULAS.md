# Dashboard Formulas — every metric, exactly how it's computed

Source: `vinayak/schema/queries.py`. Notation: `Σx` = SUM, `#distinct x` = COUNT(DISTINCT x),
`#x` = COUNT(*). All queries filter `WHERE company_id = <brand>` first (tenant isolation).

> **Root-cause note.** The earlier "huge numbers" were caused by duplicate rows: the
> sync inserted the same record on every run (7×–32× copies). That has been fixed —
> rows are now deduplicated and the sync upserts in place — so every Σ and count below
> now operates on one row per real record.

## Two revenue/spend bases (shown separately on the cards)

- **Goods value** = `Σ line_total` — the sum of line items, **excludes tax/freight**.
- **Invoice total** = `Σ (per-invoice MAX(invoice_total))` — the printed invoice grand
  total, **includes tax/freight**. (We collapse each invoice to one header value first,
  so multi-line invoices aren't multiplied.)

Goods is always slightly less than Invoice total (the difference is tax/freight).

---

## Date windows

`_resolve_window` decides the [start, end] every windowed query uses:

- If you pick a range, it's honored.
- Otherwise the window is the last `period_days` (default 30) counted back from the
  **latest available data date**, not today — so panels are never empty just because
  the last sync is a few days old. Every summary panel now uses this rule.

`monthly_avg` is a true trailing-12-month average: `Σ / (number of distinct months
that actually have data)`, anchored to the latest data.

---

## Sales / Revenue

**Revenue Overview** (`get_revenue_summary`)

- Revenue · goods = `Σ line_total` over window
- Revenue · invoice total = `Σ per-invoice MAX(invoice_total)` over window
- Invoices = `#distinct invoice_number`
- Customers = `#distinct customer_code`
- Avg / Invoice = `(Σ invoice header total) / #distinct invoice_number`
- Monthly Avg (12mo) = trailing-12-month goods Σ ÷ distinct months (also an invoiced variant)
- YTD goods / YTD invoiced = same two bases for `year = latest-data year`

**Revenue Trend** (`get_revenue_trend`) — per calendar month: revenue = `Σ line_total`,
invoices = `#distinct invoice_number`; missing months filled with 0; last 6 months.

**Daily Revenue** (`get_revenue_daily`) — per day: revenue = `Σ line_total`,
invoices = `#distinct invoice_number`; gap-filled; default last 90 days.

**Customer Concentration** (`get_customer_concentration`) — top 5 customers by
`Σ line_total`, plus an "Others" slice = `total − Σ(top 5)`. Percentages are each
customer's share of the window total.

**Top Customers** (`get_top_customers_revenue`) — per customer: revenue = `Σ line_total`,
invoices = `#distinct invoice_number`, pct = `100 × customer revenue / grand total`. Top 15.

**Top SKUs** (`get_top_skus_revenue`) — per SKU: revenue = `Σ line_total`,
qty = `Σ quantity`, invoices = `#distinct invoice_number`. Top 20.

---

## Purchases

**Purchases** (`get_purchases_summary`)

- Spend · goods = `Σ line_total`; Spend · invoice total = `Σ per-invoice MAX(invoice_total)`
- Monthly Avg = trailing-12-month goods Σ ÷ distinct months (+ invoiced variant)
- Active Vendors = `#distinct vendor_name`; Invoices = `#distinct invoice_number`
- Overdue POs = `# POs` past `expected_date` whose status isn't received/cancelled
  (status compared case-insensitively)

**Top Vendors** (`get_top_vendors_spend`) — per vendor: spend = `Σ line_total`,
invoices = `#distinct invoice_number`, pct of total. Top 10.

---

## Inventory (live snapshot — no date window)

**Inventory** (`get_inventory_summary`)

- Total Value = `Σ total_value`
- SKUs Tracked = `#distinct sku_code`
- Zero/Negative Stock = `# rows where quantity < 0`
- Warehouses = `#distinct warehouse`

**By Category** (`get_inventory_by_category`) — per category: value = `Σ total_value`,
SKUs = `#distinct sku_code`. Top 15 by value.

**Top Stock Holdings** (`get_top_stock_holdings`) — SKUs with `quantity > 0`, ranked by
`total_value`. Top 20.

---

## Production

**Production** (`get_production_summary`)

- FG Produced = `Σ produced_qty`; Rejected = `Σ rejected_qty`
- Reject Rate = `100 × rejected / (produced + rejected)`
- WIP Jobs = `#distinct work_order_number where status = 'wip'` (case-insensitive)
- Completed = `#distinct work_order_number` where status is completed/closed **or**
  `produced_qty ≥ planned_qty`

**WIP Detail** (`get_production_wip`) — per status: count, `Σ planned_qty`, `Σ produced_qty`;
plus the 30 most recent WIP work orders.

---

## Quotations & GRN

**Quote Pipeline** (`get_quote_summary`)

- Won = `# quotes where converted_to_order OR status in (won, accepted)`; Won value = `Σ quoted_value` of those
- Open = `# quotes` not won/lost/rejected/cancelled; Open value = `Σ quoted_value` of those
- Conversion Rate = `won count / total quotes`

**GRN** (`get_grn_summary`)

- GRNs Received = `#distinct grn_number`
- Rejection Rate = `Σ rejected_qty / Σ received_qty`
- Pending QIR = `# rows where rejected_qty IS NULL`
- Total value = 0 (the source report carries no monetary value)

**BOM Coverage** (`get_bom_coverage`) — `coverage = distinct manufactured SKUs that have a
routing / distinct manufactured SKUs`.

---

## Orders & AR (operational)

**Open Sales Orders** (`get_order_book_summary`)

- Open Orders = `# orders` whose status ∉ {dispatched, cancelled} (case-insensitive)
- Open Value = `Σ order_value` of those
- Dispatched % = `100 × #dispatched / #total`
- Overdue = `# open orders` past `delivery_date`

**AR Aging** (`get_ar_summary`) — per bucket: count + `Σ outstanding_amount`;
Overdue = those with `days_overdue > 0`; Total Outstanding = `Σ outstanding_amount`;
top 15 customer exposures by outstanding. (AR is a pre-aggregated snapshot.)

**AR Exposure** (`get_ar_customer_exposure`) — per customer: outstanding, invoice count,
max days overdue, overdue value. Top 15.

**Open POs** (`get_open_pos`) — Open = status ∉ {received, cancelled}; Overdue = open subset
past `expected_date`; both as count + `Σ po_value`; by-vendor top 10. (All status checks
case-insensitive.)

**Overdue POs / Orders** (`get_overdue_pos`, `get_overdue_orders`) — rows past their
expected/delivery date and still open; totals + top 25 list.

---

## Detail tables (paginated lists)

For sales invoices, purchase invoices, sales orders, purchase orders, production, inventory,
and AR:

- The footer **"of N"** is `#rows` (row count) — never a money sum.
- Date window defaults to the full data span when no range is chosen.
- Search matches the relevant name/number/code columns; sort and pagination are server-side.
