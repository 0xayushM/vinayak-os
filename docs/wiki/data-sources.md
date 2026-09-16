# Data sources

| Source | Kind | What it gives | Quirks | Reconnect |
|---|---|---|---|---|
| TranzAct | Manufacturing ERP, cloud reporting API | 10 reports: sales invoices (item-wise), AR aging, sales orders, purchase invoices, POs, GRN/QIR, quotations, inventory valuation, item BOM, process details | No server-side date filter — history is read by page-walk (newest first); ~10 req/min limit (we use 8); report ids became per-company UUIDs in Aug 2026 — resolved by function name via the catalogue; no cost data, no payment receipt dates | Settings → TranzAct → re-enter credentials → Test → Sync |
| Zoho Books | Accounting, REST v3 | Contacts, items, invoices, bills (headers), payments | Provisional — not yet verified on a live org; list endpoints are headers only | Settings → Add source → Zoho |
| Tally | Desktop accounting (planned) | Ledgers, vouchers, bills outstanding, stock items — including payment dates and AP | Needs the on-premises bridge; see reference §9 | — |
| CSV uploads (planned) | Costs per SKU, customer contacts | Unlocks margin and sends | — | — |

## Field-level quirks worth knowing

These are the ones that have already caused a wrong number on a screen. Add to
the list whenever the eval's factual grading or a sync argument turns one up.

### `canon_sales_order_flat` is line-level; counts must be per order

One live workspace holds **398 rows for 64 orders**. Every `COUNT(*)` over this
view counts lines, so "overdue orders" read 392 when the true figure was 22 —
a number that was on the dashboard for weeks and is impossible to sanity-check
by eye, because nobody knows offhand how many sales orders the business has.

Rules: **counts** use `COUNT(DISTINCT order_number)`; **values** are summed over
lines, which is right — `order_value` is genuinely a per-line figure, not the
order total repeated. The same discipline is applied to purchase orders even
though that source currently gives one line per PO.

### `pending_qty` is populated for sales orders and not for purchase orders

TranzAct fills `pending_qty` on sales orders and leaves `ordered_qty`,
`received_qty` and `pending_qty` at `0.0` on every purchase order, where the
only signal is `status` (always `Sent` in the data we have).

So there is no single rule for "still open". `queries.order_lines_carry_pending`
asks the data per company and per table, and the query branches: where
quantities exist they are the truth about what is outstanding; where they do
not, status is all there is. An order with nothing pending has been delivered
whatever its status says, which is why the pending-based rule is preferred when
it is available.

The consequence for PO figures: we can verify that the engine counts purchase
orders rather than lines, but **not** that its open/closed rule is right —
there is nothing independent to check it against until Tally or a CSV brings
receipt quantities. `eval/oracles.py` says so in the oracle's own docstring
rather than pretending to a check it cannot make.
