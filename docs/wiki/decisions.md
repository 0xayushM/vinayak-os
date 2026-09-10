# Decisions

Newest first. One line each: date · decision · why. Longer rationale lives in
`docs/reference/` (HLD §11 has the architectural ones).

- 2026-09-09 · Milestone evidence lives in the product (usage_events, experiments, incidents, eval_runs) · so the month-6 review is evidence, not an argument.
- 2026-09-10 · The milestone *tracker* is a document (`docs/reference/MILESTONES.md`), not a screen · a review is a conversation about what was agreed and why a criterion is judged as it is, which a table cannot hold; `python -m vinayak.scripts.milestone_status` prints the countable half. The board page was built in Sprint 0 and removed.
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

---

## 2026-09-10 — The brain runs in its own process, on a table-backed bus

**Decision.** Background work moves out of the API into `python -m vinayak.worker`,
a second Railway service off the same image. The API starts no scheduler unless
`RUN_SCHEDULER=1` (which `dev.sh` sets, so local development stays one command).

**Why.** The API is horizontally scaled. A scheduler inside it runs every job
once per replica — invisible today with one replica, and a data-corrupting
surprise the day there are two. It also means a four-minute sync competes with
requests a person is waiting on, and a crash loop in a watcher takes the
dashboard down with it.

**Decision.** The event bus is a Postgres table, not Redis or a broker.

**Why.** Volume is a few hundred events per company per day. A broker would add
infrastructure that can fail without buying anything a table cannot do, and the
table buys two things a broker does not: an event is written in the same
transaction as the data that produced it, and last week's events are still
there when somebody asks why the brain did something.

**Decision.** Every event carries a `dedupe_key` that identifies the FACT, not
the row — `INV-4471:rung60`, `inventory_valuation:2026-09-10`.

**Why.** Detectors are pure functions of the current data and run every few
hours, so they re-derive the same facts on every pass. Without the key, "this
invoice is 60 days late" becomes an event every three hours until it is paid,
and the customer gets chased every three hours with it. The unique index is
what turns a repeated derivation into a single fact.

**Decision.** Only one of the three detectors produces an action.

**Why.** An overdue invoice has an obvious, safe, reversible response: draft a
reminder for a person to approve. A stale feed and an anomaly do not — nobody
wants the brain "fixing" a pipeline or writing off negative stock. Those events
are recorded, surfaced, and closed with the reason they produced no action.
Writing the reason down is the point: an event deliberately left alone and an
event silently dropped look identical from the outside, and only one is a bug.

## 2026-09-10 — An experiment's metric is a key, not a sentence

**Decision.** `brain/metrics.py` holds the small set of numbers an experiment
can be judged on. Each declares its direction. The verdict rule is fixed:
reached the target, or moved ≥10% the right way → positive; moved ≥5% the wrong
way → negative; anything else, or unreadable → inconclusive.

**Why.** An experiment is only real if somebody can say afterwards whether it
worked, and that is only true if the metric was chosen before it ran and can be
read the same way twice. Direction has to be declared because "went down" is
good news for overdue money and bad news for revenue. And `inconclusive` has to
be a real outcome, not a failure to have one — most business experiments end
there, and a log that pretends otherwise is a log nobody trusts when it does
say positive.

**Decision.** Any Inbox approval can be tagged "run as experiment".

**Why.** The hard part of "run 30 experiments" is remembering to call something
an experiment while you are doing it. Most of what the owner approves already
is one. Tagging captures the baseline at approval, sets a window, and lets
`experiments.close` read the metric again weeks later — so an ordinary working
morning produces logged experiments with real outcomes.

## 2026-09-10 — Today can no longer return an error

**Decision.** `/dashboard/pulse` catches everything and returns a card that
says it could not be built, with the traceback in the server log.

**Why.** It shipped with a 500 on both live workspaces. The cause was
migrations 019–021 not having been applied: `user_record` selects columns
migration 020 adds, that SELECT failed, and the aborted transaction then broke
the next query on the same connection — so a *preference lookup* took the whole
page down. Both halves are fixed (rollback on failure, and a fallback query),
but the structural lesson is the one worth keeping: Today is the page the owner
opens first, and a blank one saying "Internal server error" is worse than any
partial answer.

## 2026-09-10 — Daily overview comes back

**Decision.** The single screen showing every panel is restored, above Money in.

**Why.** Cutting fourteen pages to four removed real duplication, but it also
removed the morning scan — the screen you read to confirm everything is roughly
where you left it. That is a different job from "where is money stuck in this
loop", and the repetition it involves is the feature, not the bug.
