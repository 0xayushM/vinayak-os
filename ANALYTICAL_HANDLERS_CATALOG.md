# Analytical Handlers Catalog — Manufacturing & Distribution

What questions the AI should be able to answer, grounded in how SMB manufacturers
and distributors actually run their businesses. Each handler = one analytical
capability the deterministic engine computes (the LLM only narrates it).

**How to read the status column**
- ✅ **Ready** — we have the data; build it now.
- ⚠️ **Partial** — buildable but approximate, or needs a small data addition.
- ❌ **Blocked** — needs data we don't sync yet (noted); the right behaviour is an
  honest UNCERTAIN + a "teach me / connect this" prompt.

**Already built** (15): revenue, revenue_trend (now with MoM decline detection),
concentration, top_customers, receivables, payment_stretch, dead_stock (real
non-movement), top_skus, purchases, inventory, overdue_pos, overdue_orders,
margin (refuses), forecast (refuses), creditworthy (refuses).

The catalog below is the target set to grow into. Priority: **P0** = high value +
data ready, **P1** = ready, second wave, **P2** = needs a data source first.

---

## A. Sales & Revenue

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `revenue` ✓ | "How much did I sell [period]?" | Σ sales over window | ✅ | done |
| `revenue_trend` ✓ | "Which months declined?" | MoM deltas, flag drops, outliers | ✅ | done |
| `sales_compare` | "This month vs last / this year vs last year?" | Two windows side by side + % change + driver split | ✅ | **P0** |
| `sales_by_category` | "Which product categories sell most / are shrinking?" | Σ line_total grouped by category, trend | ✅ | **P0** |
| `sales_by_salesperson` | "Who are my best salespeople?" | Σ revenue by salesperson, vs prior period | ✅ | P1 |
| `revenue_run_rate` | "At this pace, where do I land this year?" | annualise trailing run-rate (label as projection, PROBABLE) | ✅ | P1 |
| `daily_sales_pattern` | "Which days/weeks are strong or weak?" | daily series, weekday pattern | ✅ | P2 |

## B. Customers

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `concentration` ✓ | "Am I too dependent on a few buyers?" | top-N share of sales, risk flag >50% | ✅ | done |
| `top_customers` ✓ | "Who are my biggest customers?" | rank by revenue | ✅ | done |
| `customer_changes` | "Which customers grew or shrank vs last period?" | revenue this vs prior window per customer; rank movers | ✅ | **P0** |
| `new_lost_customers` | "Who's new, and who stopped buying?" | first-seen / last-seen invoice date per customer | ✅ | **P0** |
| `at_risk_customers` | "Who looks like they're slipping away?" | falling order frequency / value + ageing last purchase | ✅ | **P0** |
| `customer_profile` | "Tell me everything about customer X" | one-customer 360: revenue, AR, terms (memory), trend, top SKUs | ✅ | **P0** |
| `customer_payment_behaviour` | "Who actually pays on time vs late?" | avg days-to-clear per customer (needs paid date) | ⚠️ | P1 |
| `customer_profitability` | "Which customers actually make me money?" | gross profit by customer | ❌ (COGS) | P2 |

## C. Receivables & Collections (the cash-flow heart)

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `receivables` ✓ | "Who owes me, who's overdue?" | AR total/overdue + top exposures | ✅ | done |
| `payment_stretch` ✓ | "Who's stretching their terms?" | open-invoice age vs saved terms (memory) | ✅ | done |
| `dso` | "How many days to get paid? Trending up?" | Days Sales Outstanding = AR ÷ (sales/day); track over time | ⚠️ | **P0** |
| `collections_priority` | "Who should I chase first this week?" | rank overdue by amount × days-overdue (recovery impact) | ✅ | **P0** |
| `ar_concentration` | "Is my overdue stuck in one or two customers?" | overdue share by customer | ✅ | **P0** |
| `credit_exposure` | "Who's over their credit limit?" | outstanding vs saved credit_limit (memory) | ⚠️ | P1 |
| `bad_debt_risk` | "What's at risk of never being collected?" | 90+ bucket value + oldest invoices | ✅ | P1 |

## D. Inventory

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `inventory` ✓ | "How much stock am I holding?" | Σ stock value, SKU count | ✅ | done |
| `dead_stock` ✓ | "What's just sitting there?" | held SKUs with no sale in N days + value tied up | ✅ | done |
| `inventory_turnover` | "How fast is my stock moving?" | turns = sales ÷ avg inventory (DIO = 365/turns); per category | ⚠️ | **P0** |
| `reorder_alert` | "What am I about to run out of?" | qty_on_hand vs recent sales velocity → days-of-cover | ✅ | **P0** |
| `overstock` | "Where am I carrying too much?" | days-of-cover far above norm; excess capital | ✅ | P1 |
| `negative_stock` | "Where are my stock records wrong?" | qty < 0 rows (data-quality / leakage) | ✅ | P1 |
| `gmroi` | "Which products earn their shelf space?" | gross margin ÷ avg inventory cost | ❌ (COGS) | P2 |
| `stockout_impact` | "What sales did I lose to stockouts?" | zero-stock SKUs with prior demand | ⚠️ | P2 |

## E. Purchasing & Vendors

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `purchases` ✓ | "What did I spend, with whom?" | spend + top vendors | ✅ | done |
| `vendor_concentration` | "Am I too reliant on one supplier?" | top-N share of spend, single-source risk | ✅ | **P0** |
| `purchase_price_trend` | "Is a vendor/material getting more expensive?" | unit-price trend per item/vendor over time | ✅ | **P0** |
| `dpo` | "How long do I take to pay suppliers?" | Days Payable Outstanding (needs paid date) | ⚠️ | P1 |
| `spend_changes` | "Where did my costs jump this period?" | spend this vs prior window by vendor/category | ✅ | P1 |
| `purchase_vs_sales` | "Am I buying in line with what I'm selling?" | purchase volume vs sales volume by item | ⚠️ | P2 |

## F. Orders & Fulfilment

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `open_order_book` | "What's my confirmed forward demand?" | open sales orders value + by customer/age | ✅ | **P0** |
| `overdue_orders` ✓ | "Which deliveries are late?" | past delivery date, not dispatched | ✅ | done |
| `overdue_pos` ✓ | "Which incoming POs are late?" | past expected date, not received | ✅ | done |
| `fill_rate` | "Am I shipping orders complete & on time?" | dispatched vs ordered qty; on-time % | ⚠️ | P1 |
| `order_to_cash_time` | "How long from order to payment?" | order_date → invoice → paid (stage durations) | ⚠️ | P2 |

## G. Production (manufacturing)

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `production_summary` | "What's in progress / completed?" | WIP vs completed work orders, output | ✅ | P1 |
| `reject_rate` | "How much am I scrapping, and where?" | rejected ÷ produced, by SKU/process | ✅ | **P0** |
| `production_vs_demand` | "Am I making what's selling?" | produced qty vs sold qty by SKU | ⚠️ | P1 |
| `bom_coverage` | "Which products lack a defined routing?" | manufactured SKUs without routing | ✅ | P2 |
| `throughput_trend` | "Is output rising or falling?" | produced qty over time | ✅ | P2 |

## H. Quotes & Pipeline

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `quote_conversion` | "What % of quotes turn into orders?" | won ÷ total quotes; trend (early pricing/competitive signal) | ✅ | **P0** |
| `open_quotes` | "What's in my quote pipeline?" | open quote value + age | ✅ | P1 |
| `lost_quote_reasons` | "Why am I losing quotes?" | lost-quote analysis (needs reason field) | ❌ | P2 |

## I. Working capital & cash

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `cash_conversion_cycle` | "How long is my cash tied up?" | CCC = DIO + DSO − DPO | ⚠️ | **P0** (huge value) |
| `working_capital_snapshot` | "Where's my cash locked — stock, receivables?" | inventory value + AR − AP composition | ⚠️ | **P0** |
| `cash_gap_alert` | "Will I have a cash crunch soon?" | expected inflows (AR due) vs outflows (PO/AP due) timeline | ⚠️ | P1 |
| `profit_vs_cash` | "I'm profitable but where's the cash?" | sales vs collected vs stock build-up explanation | ⚠️ | P1 |

## J. Profitability & margin

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `margin` ✓ | "What's my margin?" | refuses — no COGS synced | ❌ (COGS) | done (refuses) |
| `gross_profit_by_x` | "Where do I actually make money?" | GP by product/customer (the #1 hidden insight) | ❌ (COGS) | P2 |
| `margin_estimate` | "Roughly, what's my margin?" | apply owner-confirmed margin % (memory) to revenue | ⚠️ | P1 |
| `price_realisation` | "Am I discounting too much?" | actual unit_price vs list/standard (needs list price) | ❌ | P2 |

## K. Cross-cutting intelligence

| Handler | Owner question | Logic | Status | Priority |
|---|---|---|---|---|
| `anomaly_scan` | "Anything unusual this month?" | flag metrics deviating from trailing average (spikes/drops) | ✅ | **P0** |
| `why_changed` | "Why did revenue/AR move?" | decompose a delta into the customers/SKUs that drove it | ✅ | **P0** |
| `period_compare` | "Compare any metric across two periods" | generic two-window diff for any metric | ✅ | **P0** |
| `business_pulse` | "Give me the morning briefing" | one-shot: sales, overdue AR, late orders, anomalies, dead stock | ✅ | **P0** |
| `kpi_vs_benchmark` | "How do I compare to a healthy business?" | metric vs owner/industry benchmark (memory/profile) | ⚠️ | P1 |

---

## The data gaps that unlock whole categories

A few missing inputs are blocking the highest-value analytics. Worth prioritising
the data work, because each one lights up several handlers:

1. **Cost of goods / purchase cost per SKU** → unlocks margin, gross-profit-by-customer/product, GMROI, price realisation (Category J + parts of B, D). This is the single biggest unlock and the #1 hidden-insight metric for these businesses.
2. **Payment cleared dates (receipts) & supplier paid dates** → unlocks DSO, DPO, the full cash-conversion-cycle, and real payment-behaviour scoring (Category C, E, I). We have AR outstanding but not the actual collection timeline.
3. **Reliable last-movement / per-SKU velocity** → already approximated via sales cross-reference (dead_stock); a true stock-ledger would sharpen turnover, reorder, overstock (Category D).
4. **List/standard price & quote reason codes** → price realisation, lost-quote analysis (J, H).

Until those land, the right behaviour is the one already built: compute what's
possible, and for the rest return an honest UNCERTAIN with a "connect this data /
tell me your margin" prompt — never a fabricated number.

---

## Suggested build order (P0 first)

**Wave 1 — cash & customers (ready now, highest owner value):**
`business_pulse`, `cash_conversion_cycle` (approx), `dso`, `collections_priority`,
`customer_changes`, `new_lost_customers`, `at_risk_customers`, `customer_profile`,
`reorder_alert`, `inventory_turnover`, `vendor_concentration`, `purchase_price_trend`,
`quote_conversion`, `reject_rate`, `anomaly_scan`, `why_changed`, `period_compare`,
`sales_compare`, `sales_by_category`, `open_order_book`, `ar_concentration`.

**Wave 2 — ready, second priority:** `bad_debt_risk`, `overstock`, `negative_stock`,
`spend_changes`, `production_summary`, `production_vs_demand`, `open_quotes`,
`fill_rate`, `revenue_run_rate`, `sales_by_salesperson`, `margin_estimate`,
`credit_exposure`, `customer_payment_behaviour`, `working_capital_snapshot`,
`cash_gap_alert`, `profit_vs_cash`, `kpi_vs_benchmark`.

**Wave 3 — needs a data source first:** `customer_profitability`, `gmroi`,
`gross_profit_by_x`, `dpo` (precise), `price_realisation`, `lost_quote_reasons`,
`stockout_impact`, `order_to_cash_time`, `purchase_vs_sales`, `bom_coverage`,
`throughput_trend`, `daily_sales_pattern`.

Every new handler ships with a golden eval case so the numbers stay guaranteed.

---

### Sources
- [10 KPIs SMB owners should track (AccountingDepartment)](https://www.accountingdepartment.com/blog/10-key-performance-indicators-smb-owners-should-track-for-business-growth-in-2025)
- [How to decide which KPIs to track in a manufacturing shop (Lasso Supply Chain)](https://lassosupplychain.com/resources/blog/how-to-decide-which-kpis-to-track-in-your-manufacturing-shop-a-step-by-step-framework-for-smbs/)
- [Top financial metrics for small business (NetSuite)](https://www.netsuite.com/portal/resource/articles/financial-management/small-business-financial-metrics.shtml)
- [Top 35+ distribution KPIs (insightsoftware)](https://insightsoftware.com/blog/distribution-kpis-and-metric-examples/)
- [Inventory management KPIs for distributors (Enavate)](https://www.enavate.com/blog/8-useful-inventory-management-kpis-for-distributors)
- [Wholesale distribution KPIs (NetSuite)](https://www.netsuite.com/portal/resource/articles/inventory-management/wholesale-distribution-kpi.shtml)
- [Slow customer payments in manufacturing (American Receivable)](https://americanreceivable.com/slow-customer-payments-in-manufacturing-how-to-protect-your-cash-flow-and-keep-production-moving/)
- [Profitable but running out of cash (Ramp)](https://ramp.com/blog/are-you-turning-a-profit-but-running-out-of-cash)
- [Cash conversion cycle (Corporate Finance Institute)](https://corporatefinanceinstitute.com/resources/accounting/cash-conversion-cycle/)
- [Understanding & optimizing your CCC (J.P. Morgan)](https://www.jpmorgan.com/insights/treasury/receivables/understanding-and-optimizing-your-cash-conversion-cycle)
