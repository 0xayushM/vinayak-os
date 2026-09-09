# Business dictionary

What each term on a screen actually means. Copied from the BIDE reference
(Part 5.3) and extended as new cards appear.

| Term | Meaning |
|---|---|
| Revenue / Sales | Money earned from selling, counted when the invoice is raised, not when cash arrives |
| Goods value | Line items only (price × qty), excluding tax and freight — the real trading value |
| Invoice total | The printed grand total including tax and freight |
| AR (receivables) | Everything customers owe right now — raised but unpaid invoices |
| Outstanding / Overdue | Outstanding = all unpaid; overdue = past due date and still unpaid |
| Aging buckets | 0-30 / 31-60 / 61-90 / 90+ days late; 90+ is the one to worry about |
| Aging drift | Value that moved into worse buckets over a window — "is money sliding toward bad?" |
| Exposure | What we would lose if one customer never paid — their total outstanding |
| DSO | Average days between invoicing and getting paid; lower is better |
| Concentration | Share of revenue from the top few customers — the dependence risk |
| AP (payables) | The mirror of AR — what we owe vendors |
| PO / GRN / QIR | Purchase order; goods received note; quality inspection report |
| Inventory value | Quantity on hand × unit value, summed across SKUs |
| Dead stock / trapped capital | Items with no sales in 90 days — money frozen on a shelf |
| Days of cover | Days before an item runs out at the recent sales rate |
| Reorder radar | Regular buyers who are past 1.5× their own usual gap between orders |
| Order book | All open sales orders — future revenue already agreed |
| Margin / COGS | Selling price minus cost — needs cost per SKU, which we do not have from TranzAct |
| Confidence label | CERTAIN (computed from complete data) · PROBABLE (a proxy or an inference) · UNCERTAIN (cannot answer reliably) |
| Stale | Last sync older than 25 hours; the number still shows but is flagged |
| Experiment | A change we tried, with a metric, a window, and an outcome |
| Watcher | A background rule that detects something and prepares an action for approval |
