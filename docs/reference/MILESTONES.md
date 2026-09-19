# Milestones — the tracker

> **This file is the tracker.** There is no milestone screen in the product, on
> purpose: a milestone review is a conversation with Shourya and Sandeep, and a
> document can hold what a table cannot — what was agreed, what changed, and why
> a criterion is judged the way it is. The countable half comes from the database:
>
> ```bash
> python -m vinayak.scripts.milestone_status          # every workspace
> python -m vinayak.scripts.milestone_status kbrushes # one
> ```
>
> Paste its output into **Where the numbers stand** below and date it. Update
> this file at the end of every sprint, in the same commit as the work.
>
> The compensation terms behind these milestones are deliberately not reproduced
> here. The Busy integration criterion was dropped by agreement and is not tracked.

**Status legend** — ✅ met · 🟢 on track · 🟡 at risk / not yet measurable · 🔴 not started · ⬜ needs confirmation outside the repo

---

## The clock

| Date | What |
|---|---|
| **1 Sep 2026** | Start |
| **1 Dec 2026** | Month-3 demo |
| **1 Mar 2027** | Milestone 1 review (latest acceptable **1 May 2027**) |
| **1 Sep 2027** | Milestone 2 review (latest **1 Nov 2027**) |
| **1 Sep 2028** | Milestone 3 review (latest **1 Mar 2029**) |

Two criteria have clocks that cannot be compressed near the end, and they set the
whole sequencing of `PLAN.md`:

1. **The 60 consecutive days of use.** The first qualifying week has to begin
   by **Monday 2 Nov 2026**: nine weeks then end on 3 Jan, leaving January and
   February for a restart if a week is missed — and the month-3 demo needs four
   qualifying weeks before 30 Nov anyway. Monday 28 Dec is the arithmetic last
   chance and has no room for a single light week. That is what made the Pulse landing
   page and the 06:00 brief the first things built.
2. **30 experiments with outcomes.** At roughly six a month from October, with a
   six-week average window, the last one has to be *started* by mid-January.

---

## Where the numbers stand

**kbrushes**

_Read on 2026-09-17 from workspace `kbrushes`._

| Criterion | Where it stands |
|---|---|
| Owner active ≥ 4 days/week for 60 consecutive days | no tracked user set (`milestone_user_email` in `platform_settings`) |
| 50-question eval: ≥ 80% factual, 100% citation | 58 cases (freeze at 50) · citation 100% · factual 100% (runner `engine`, 2026-09-16) |
| ≥ 30 logged experiments with outcomes | 0 with outcomes of 6 logged · 5 AI-suggested, 0 acted on |
| No critical incident in the last 60 days | none recorded in the last 60 days |

Month-3 demo **2026-12-01** · month-6 review **2027-03-01** (165 days away) · latest acceptable **2027-05-01**.

**protegere**

_Read on 2026-09-17 from workspace `protegere`._

| Criterion | Where it stands |
|---|---|
| Owner active ≥ 4 days/week for 60 consecutive days | no tracked user set (`milestone_user_email` in `platform_settings`) |
| 50-question eval: ≥ 80% factual, 100% citation | 58 cases (freeze at 50) · citation 100% · factual 100% (runner `engine`, 2026-09-16) |
| ≥ 30 logged experiments with outcomes | 0 with outcomes of 4 logged · 4 AI-suggested, 0 acted on |
| No critical incident in the last 60 days | none recorded in the last 60 days |

Month-3 demo **2026-12-01** · month-6 review **2027-03-01** (165 days away) · latest acceptable **2027-05-01**.

**What this reading says.** The brain is running and producing: 12 watcher
passes, 33 events, 10 experiments suggested by the Strategy watcher and 7
chase proposals waiting in the Inbox — all from live data, none of it typed in
by hand. The eval is above its target size and passing both halves.

**And every clock is still at zero.** No tracked user is set, so criterion 2's
60-day window has not begun; no experiment has been *accepted*, so none can
close, and 30 with outcomes is the criterion. Neither is an engineering
problem. The binding constraint is criterion 2: the window has to start by
**Monday 2 Nov**. The 17 Sep reading is unchanged from the 16th on every count —
which is itself the finding: nothing moves these numbers except a person.

---

## Milestone 1 — "The Brain Works"

**Target** end of month 6 (1 Mar 2027) · **latest** month 8 (1 May 2027).
**Verification** end-of-month-6 review with Shourya, Sandeep and Ayush; pass/fail
decided by Shourya with Sandeep's confirmation. **All** criteria must be true.

### 1 · The dashboard is live in production — 🟢

Vercel (web) + Railway (API and worker) + Supabase (Postgres and auth), CI on
every push. Today is the landing page: nine decision cards, each naming a delta,
a cause or a decision, plus the 06:00 IST brief by email.

**Done 19 Sep:** migrations 024–025 applied; the worker runs as its own Railway
service (start command in the dashboard, see `Procfile`) — the syncs, the brief
and the brain no longer depend on the API process.

**Left:** set `ALERT_EMAIL` and an email provider on both services (until then
nothing is emailed — briefs, chases or alerts); move web's healthcheck and restart
policy out of `railway.json` into the dashboard before **1 Dec**, when Railway
stops reading config files; confirm the workspace Sandeep opens is the one that
is connected and syncing. ⬜

### 2 · Sandeep has used it ≥ 4 days/week for 60 consecutive days — 🟡

The rule is stated once, in `vinayak/usage.py`: a week (Mon–Sun) qualifies when
he was active on ≥ 4 distinct days; a run is consecutive qualifying weeks; the
criterion is met when a run covers ≥ 60 days (9 weeks = 63 days; 8 = 56 does
not). `usage_events` records one row per user per workspace per day on every
authenticated request — it is written automatically and needs no screen.

**Left:** set `milestone_user_email` in `platform_settings` to Sandeep's address;
onboard him (his workspace, his role, the brief to his inbox, one walkthrough in
person); **first qualifying week to begin by Monday 2 Nov 2026**.

### 3 · 50-question eval: ≥ 80% factual accuracy, 100% citation compliance — 🟡

60 candidate cases today. The harness grades citation compliance (100% on the
deterministic path), refusal, intent and bucket, gates CI, and `--record` writes
each run to `eval_runs` so the numbers above are real rather than remembered.

**Factual accuracy is now measured.** `eval/oracles.py` recomputes each fact a
second way, sharing no code with `schema/queries.py`, and twelve cases name an
Evidence id and an oracle. Only window-free facts are graded — total
outstanding, stock value, overdue counts, identities like the largest debtor —
because "revenue in the period" depends on a period the engine chooses, and an
oracle that re-derived it would be copying the answer. Seventeen figures are
checked per workspace, and the metric reports `None` rather than `1.0` when
nothing is checkable.

**It found a real fault on its first run.** `canon_sales_order_flat` is
line-level — 398 rows for 64 orders — and every count was `COUNT(*)`, so the
engine and the dashboard reported **392 overdue orders where there were 22**.
Fixed; counts are now per order, values still per line. The same run showed
that `pending_qty` is populated for sales orders and never for purchase orders,
so "still open" branches on what the source actually provides.

**The set is at 60, written from the auditor's side.** The second half was
built by working through a statutory review as the group's CA would and
checking each question against the data we actually sync — see
`docs/wiki/auditor-view.md`. Sixteen of the sixty are refusals, because a third
of what a CA needs (GST, TDS, bank, P&L, creditors, depreciation) is not in an
operational ERP feed at all, and that is exactly where a confident wrong answer
would cost the most. Carrying sixty is deliberate: hand-verification will drop
some, and a set that arrives at the freeze date one case short gets padded.

**The freeze is tooling now, not a promise.** `python -m vinayak.eval.worksheet`
writes the session sheet (failing cases and refusals first, every figure beside
its oracle, three boxes per case); a `verified` record on each case captures the
sign-off; `worksheet --select` proposes a balanced 50; `python -m
vinayak.eval.frozen <ids> --write` freezes them with a content hash, refusing
unless all 50 are verified, and `--check` catches a frozen case edited later.
`harness --frozen --record` then records a run that `criterion_met` can judge:
frozen set, exactly 50 questions, ≥ 80% factual, 100% citation. Only cases that
run on both workspaces can be frozen — 58 of the 60.

**Left, in order:** two hand-verification sessions with Shourya, one per path
(`worksheet` and `worksheet --runner native`, against the eval database);
**freeze at 50 by 15 Jan 2027**; record frozen runs per workspace on both paths;
replace invented phrasings with real ones from Sandeep's Ask logs as they
accumulate (downstream of criterion 2).

### 4 · ≥ 30 logged experiments with outcomes — 🟡

`experiments` holds the log: proposed → accepted → running → closed, with a
metric, a baseline, a window and an outcome. Two things now fill it without
anyone setting aside time for it:

- the **weekly Strategy watcher** reads the Pulse and files 4–6 proposed
  experiments a week, each already written with a hypothesis, a metric key and a
  baseline captured at suggestion time;
- **any Inbox approval can be tagged "run as experiment"**, which turns an
  ordinary chase or nudge into a logged one for free.

`brain/outcomes.py` closes them when their window ends by reading the metric
again, so an experiment cannot sit open forever waiting for someone to score it.
`inconclusive` is a real outcome and counts as captured.

The morning brief now carries the queue: on Mondays the count and the three
longest-waiting suggestions, on other days one line once anything has waited
more than three days — so the decision is put in front of the person who has to
make it, rather than on a page they have to remember to visit.

**Left:** Sandeep or Shourya accepting suggestions weekly — from **now**, not
October. Ten are waiting. Only `closed` rows count, and at a 30-day window an
experiment accepted after mid-January cannot close before the review.

### 5 · ~~Busy API integration~~ — dropped by agreement, not tracked

### 6 · Month-3 demo passed; month-6 demo criteria met — 🟡

No 90-day plan existed when this started; `docs/reference/PLAN.md` now serves as
it and proposes the criteria for both demos. The month-3 demo (1 Dec 2026) is
Sandeep's own Pulse and Inbox on his own numbers — not slides.

`python -m vinayak.scripts.milestone_status --demo` reads the §4 criteria that
can be counted — brief delivered every working day, watchers on schedule,
actions executed, chases logged, customers flagged, experiments closed, active
weeks, eval runs on both paths — and marks the two that cannot as manual.
Run it weekly from October so the demo is never the first time it is checked.

**Left:** agree both sets of criteria in writing with Shourya. ⬜ Record the
month-3 outcome in the log at the bottom of this file.

---

## Half-yearly bonus criteria

### H1 — month 6

Month-3 demo passed · wiki, experiments log and dashboard v1 live in production ·
AI prototype answers a 20-question set with ≥ 75% accuracy and 100% citation
compliance · **no critical production incidents in the prior 60 days**.

- Wiki 🟢 — `docs/wiki/` (business dictionary, data sources, decisions log,
  learnings, onboarding runbook, per-company notes). Kept current every sprint.
- Incidents 🟢 — nothing in the background can now fail quietly: a failed sync,
  a halted watcher, an undelivered brief or a silent worker emails `ALERT_EMAIL`,
  and the Sync page shows worker health. What counts as critical is defined in `docs/INCIDENTS.md`, and
  **that file is now the log too**. The `incidents` table still exists and the
  status CLI counts from it; write the entry in the doc and the row in the table
  when one happens.

### H2 — month 12

Milestone 1 achieved · AI chat in production use by Sandeep **and** Shourya ·
content engine has produced ≥ 40 published pieces approved by Sandeep · Strategy
mode live with ≥ 10 AI-suggested experiments **executed**.

- Strategy mode 🟢 — live since Sprint 2; `experiments.source = 'ai_suggested'`
  and the `ai_suggested_acted_on` count is what this criterion reads.
- Content engine 🔴 — not started. Needs the knowledge plane for brand voice, a
  drafting tool, and an approval flow that records Sandeep's approval per piece
  (`BIDE_BUILD_REFERENCE.md` §7, Marketing).

---

## Milestone 2 — "The System Earns Its Keep"

**Target** end of month 12 (1 Sep 2027) · **latest** month 14 (1 Nov 2027).

All of: Milestone 1 still true · Vinayak annual revenue run-rate at month 12
≥ ₹95 Cr · ≥ ₹12 Cr of active pipeline (RFQs, quotes and recently closed)
credibly attributable to the system through **logged origination** in lead
capture, follow-up or AI suggestion · Strategy mode has produced ≥ 30 suggestions
in the year with ≥ 15 acted on · content engine ≥ 80 approved pieces.

**What this forces early.** The ₹12 Cr is an attribution claim, and attribution
cannot be reconstructed after the fact. The lead-capture hub and follow-up state
machine (Sales field) must carry an `origination` record on every lead, quote and
deal **from the day they ship**, and `pipeline_daily_snapshot` must start
recording the same day — exactly as `ar_daily_snapshot` did for receivables, and
for the same reason.

---

## Milestone 3 — "EDHway Becomes Real"

**Target** end of month 24 (1 Sep 2028) · **latest** month 30 (1 Mar 2029).

Any **one** of:

- **A** — ≥ 1 paying external MSME using it for ≥ 6 months on a paid contract.
- **B** — deployed across ≥ 3 sister companies, each company's CEO or equivalent
  active ≥ 4 days/week for 90 consecutive days.
- **C** — a strategic event: funding, acquisition offer, spin-out or licensing.

**B is the controllable one** — it is the Vinayak group rollout already planned
(`BIDE_BUILD_REFERENCE.md` §11), and it works only if usage tracking is per
company *and* per CEO from the start, which is how `usage_events` is keyed.

---

## Reporting cadence

Weekly 1:1 with Shourya · monthly review with Sandeep. Decision authority for
Track 4 (AI brain layer, wiki, experiments log, content engine) sits with Ayush
unless overridden by Shourya or Sandeep.

---

## Log

Append an entry per sprint, newest last. One paragraph: what moved, what a
criterion now stands at, and anything that changed about the criteria themselves.

**2026-09-10 · Sprints 0–2 shipped.** Milestone evidence exists and records
itself: `usage_events` (the 60-day rule, unit-tested), `experiments`, `incidents`,
`eval_runs`, roles and approval permissions. The Pulse landed as the Today page
with nine cards and the 06:00 brief, giving a reason to open the product daily —
criterion 2's precondition. The dashboard was reorganised by where money is in
its journey rather than by which ERP report it came from, then the daily overview
was restored alongside it. Sprint 2 put the brain in its own process: three
detectors, a deduplicated event bus, a consumer that proposes chases into the
Inbox, and the weekly Strategy watcher that files experiments with a metric and a
window — criterion 4's supply problem, solved. The milestone board was removed
from the product in favour of this document.

**2026-09-16 · Factual accuracy became measurable, and immediately earned its
keep.** The eval now grades the engine's Evidence against independently written
oracles. Its first run found that sales-order counts were counting lines:
392 overdue orders reported where 22 were real, a figure that had been on the
dashboard since the order book shipped. Both workspaces now pass every case at
100% citation compliance and 100% factual accuracy over 17 checked figures, and
those runs are recorded in `eval_runs`. Migration 017 was found missing and
applied — the cause of an Approvals inbox that looked empty — and migrations are
now tracked in `schema_migrations` with a startup warning, so a database behind
the code says so instead of showing a blank page.

**2026-09-16 · The auditor's half of the eval, and the brain's first real
output.** The question set went to 60, the second half written from a CA's side
of the desk: ageing thresholds, related-party billing, working capital, data
quality — and sixteen refusals, because a third of what a CA needs is not in an
operational ERP feed. Building those found that refusing by falling through is
not refusing: "creditors ageing" was returning the *debtors* ageing. `not_in_data`
is a routed intent now and names what would supply each missing answer. Nine
new intents, two new queries, both of which found something on first run —
₹50.4L of Protegere's book is over 180 days past due, and 13.9% of its revenue
is billed to a group company. Meanwhile the brain ran on live data for the
first time: 12 passes, 33 events, 10 suggested experiments, 7 chases waiting.

**2026-09-17 · Sprints 3–4, and everything left that engineering can close
without a person.** Sprints 3 and 4 shipped on the 16th, six weeks early:
collections as a process (the R1–R4 ladder climbed one rung at a time, promises,
disputes, recovery measured from delivery) and the first synapse (credit flags
raised by Accounts, shown to Sales, three asks a pass). Then the rest of what
was in our hands: the brief is now evidence — every delivery logged, HTML sent,
and the experiments waiting for a decision put in front of the person who
makes it; the contacts CSV import, so chases can reach the customers they are
for; worker heartbeat, alerting and worker health on the Sync page, for H1;
the eval freeze as tooling — worksheet, `verified` records, a hashed manifest,
`criterion_met`; and `milestone_status --demo`, which reads the month-3
criteria now rather than on 1 Dec. Found on the way: a `scripts/` ignore rule
had kept `migrate.py` and `milestone_status.py` out of git since they were
written, so the deployed startup check for missing migrations could never run
and the command this file tells everyone to use did not exist in the repo.
The start date for criterion 2 was written three different ways across the
two documents; it is **Monday 2 Nov** everywhere now. The numbers did not move
between the 16th and the 17th, and could not have: every clock left is waiting
on a person.

**Next — engineering, to deploy:** ~~apply migrations 024–025~~ ·
~~create the worker service on Railway~~ (both done 19 Sep) ·
move web's healthcheck and restart policy out of `railway.json` into the
dashboard before **1 Dec**, when Railway stops reading config files · set `ALERT_EMAIL`, an email provider and
`NEXT_PUBLIC_APP_URL` · import contacts for the overdue customers.

**Next — people, and these are the milestone:** set `milestone_user_email` to
Sandeep's address and onboard him, first qualifying week by **Mon 2 Nov** ·
Sandeep or Shourya accepting the ten waiting experiments, weekly from now ·
two eval verification sessions with Shourya, freeze by **15 Jan** · agree the
demo criteria in writing (criterion 6).
