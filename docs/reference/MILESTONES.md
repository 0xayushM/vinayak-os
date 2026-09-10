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

1. **The 60 consecutive days of use.** It has to *start* by 1 Nov 2026 to finish
   inside the window with January as buffer. That is what made the Pulse landing
   page and the 06:00 brief the first things built.
2. **30 experiments with outcomes.** At roughly six a month from October, with a
   six-week average window, the last one has to be *started* by mid-January.

---

## Where the numbers stand

_Not yet recorded — run `python -m vinayak.scripts.milestone_status` and paste the
block here. First reading due once Sandeep's workspace is live (Sprint 2 close)._

---

## Milestone 1 — "The Brain Works"

**Target** end of month 6 (1 Mar 2027) · **latest** month 8 (1 May 2027).
**Verification** end-of-month-6 review with Shourya, Sandeep and Ayush; pass/fail
decided by Shourya with Sandeep's confirmation. **All** criteria must be true.

### 1 · The dashboard is live in production — 🟢

Vercel (web) + Railway (API and worker) + Supabase (Postgres and auth), CI on
every push. Today is the landing page: nine decision cards, each naming a delta,
a cause or a decision, plus the 06:00 IST brief by email.

**Left:** deploy the Sprint 2 worker as its own Railway service; confirm the
workspace Sandeep opens is the one that is connected and syncing. ⬜

### 2 · Sandeep has used it ≥ 4 days/week for 60 consecutive days — 🟡

The rule is stated once, in `vinayak/usage.py`: a week (Mon–Sun) qualifies when
he was active on ≥ 4 distinct days; a run is consecutive qualifying weeks; the
criterion is met when a run covers ≥ 60 days (9 weeks = 63 days; 8 = 56 does
not). `usage_events` records one row per user per workspace per day on every
authenticated request — it is written automatically and needs no screen.

**Left:** set `milestone_user_email` in `platform_settings` to Sandeep's address;
onboard him (his workspace, his role, the brief to his inbox, one walkthrough in
person); **start the window by 1 Nov 2026**.

### 3 · 50-question eval: ≥ 80% factual accuracy, 100% citation compliance — 🟡

29 golden cases today. The harness grades citation compliance (100% on the
deterministic path), refusal, intent and bucket, gates CI, and `--record` writes
each run to `eval_runs` so the numbers above are real rather than remembered.

**Left, in order:** add **expected values** to the existing cases so *factual
accuracy* is graded at all — today only intent, bucket and citation are; grow to
**50 hand-verified questions**, drawn from real Ask logs rather than invented;
grade the **native agent path**, which is what production uses, in CI as a second
gate; **freeze the set with Shourya by 15 Jan 2027** so "fixed" is auditable.

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

**Left:** Sandeep or Shourya accepting suggestions weekly from October. Only
`closed` rows count.

### 5 · ~~Busy API integration~~ — dropped by agreement, not tracked

### 6 · Month-3 demo passed; month-6 demo criteria met — 🟡

No 90-day plan existed when this started; `docs/reference/PLAN.md` now serves as
it and proposes the criteria for both demos. The month-3 demo (1 Dec 2026) is
Sandeep's own Pulse and Inbox on his own numbers — not slides.

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
- Incidents 🟢 — what counts as critical is defined in `docs/INCIDENTS.md`, and
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

**Next, in order:** deploy the worker service · set the tracked user and onboard
Sandeep (criterion 2's clock, by 1 Nov) · expected values in the eval cases so
factual accuracy is graded at all (criterion 3) · agree the demo criteria with
Shourya in writing (criterion 6).
