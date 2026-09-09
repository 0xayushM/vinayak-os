# Data sources

| Source | Kind | What it gives | Quirks | Reconnect |
|---|---|---|---|---|
| TranzAct | Manufacturing ERP, cloud reporting API | 10 reports: sales invoices (item-wise), AR aging, sales orders, purchase invoices, POs, GRN/QIR, quotations, inventory valuation, item BOM, process details | No server-side date filter — history is read by page-walk (newest first); ~10 req/min limit (we use 8); report ids became per-company UUIDs in Aug 2026 — resolved by function name via the catalogue; no cost data, no payment receipt dates | Settings → TranzAct → re-enter credentials → Test → Sync |
| Zoho Books | Accounting, REST v3 | Contacts, items, invoices, bills (headers), payments | Provisional — not yet verified on a live org; list endpoints are headers only | Settings → Add source → Zoho |
| Tally | Desktop accounting (planned) | Ledgers, vouchers, bills outstanding, stock items — including payment dates and AP | Needs the on-premises bridge; see reference §9 | — |
| CSV uploads (planned) | Costs per SKU, customer contacts | Unlocks margin and sends | — | — |
