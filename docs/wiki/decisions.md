# Decisions

Newest first. One line each: date · decision · why. Longer rationale lives in
`docs/reference/` (HLD §11 has the architectural ones).

- 2026-09-09 · Milestone evidence lives in the product (usage_events, experiments, incidents, eval_runs, Milestone board) · so the month-6 review is a screen, not an argument.
- 2026-09-09 · Roles seed the dashboard layout only; two explicit permissions (approve messages, approve money) gate the Inbox · same tools, same numbers, different first screen; money never approved by someone not granted it.
- 2026-09-09 · Every business route requires the BFF's internal key · the backend URL was discoverable and the documented boundary was not enforced.
- 2026-09-09 · Google ADK stays an inert adapter behind the runner port · orchestration is not where learning lives; adopt when synapses need multi-agent handoffs.
- 2026-09-09 · Busy integration dropped from Milestone 1 by agreement.
- 2026-09-09 · BIDE becomes the ERP by owning the work upstream and posting balanced vouchers to the statutory ledger (Option A) before any full replacement.
- 2026-09-07 · TranzAct report ids resolved through the get_reports catalogue by function name · TranzAct re-keyed reports to per-company UUIDs in Aug 2026.
- 2026-09-10 · The Pulse is the landing page; a card earns its place only by naming a delta, a cause or a decision · the old overview answered "what" but never "so what", which is why it was not opened daily.
- 2026-09-10 · The morning brief is composed from card sentences with no model in the path · the cards are already built from query results, so the brief is grounded by construction rather than by a guard.
- 2026-09-10 · Comparisons are always against the business's own history (own median gap, own trailing 8 weeks, own aging history) · an SMB owner distrusts external benchmarks and trusts his own past.
- 2026-09-10 · Cards built on a proxy (payment behaviour before receipt dates, the 50% overdue-collection assumption) report PROBABLE and say what would make them certain · flagged is better than wrong.
- 2026-09-10 · The dashboard is organised by where money is in its journey (Money in / Money out / Stock & making / Customers), not by which ERP report the data came from · 14 pages were re-slicing the same five feeds; "Customer Insights" was four revenue panels. One fact now has exactly one home.
- 2026-09-10 · Each business page opens with a StageFlow showing value at every stage of a loop and what has stopped moving there · an ERP tells you what documents exist; the owner's question is where value is stuck.
- 2026-09-10 · Stages with no data say what is missing instead of showing a zero (payables, until vendor bills are synced) · a zero looks like a fact.
- 2026-09-10 · Old routes (/overview, /finance, /ar, /orders, /quotes, /skus, /purchases, /pos, /grn, /inventory, /production, /bom) redirect into the new pages rather than 404 · bookmarks and links inside briefs keep working.
