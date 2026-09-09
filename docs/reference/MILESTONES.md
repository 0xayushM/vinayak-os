# BIDE Milestones — acceptance criteria and status

> The contractual milestones for the Vinayak Brain / EDHway build, as agreed with
> Shourya and Sandeep, with each criterion mapped to what exists in the codebase.
> This file is the checklist we track against; the compensation terms that sit
> behind these milestones are deliberately not reproduced here.
>
> Status legend: ✅ met · 🟡 partly / not yet measurable · 🔴 not started · ⬜ needs confirmation outside the repo
>
> Start date: 1 Sep 2026. Month-3 demo: 1 Dec 2026 · Milestone 1 review: 1 Mar 2027 (latest 1 May 2027) · Milestone 2: 1 Sep 2027 (latest 1 Nov 2027) · Milestone 3: 1 Sep 2028 (latest 1 Mar 2029).
> Last reviewed: 2026-09-09. The Busy integration criterion has been dropped by agreement and is not tracked.

## Milestone 1 — "The Brain Works" (target: end of month 6; latest month 8)

Verification: end-of-month-6 review with Shourya, Sandeep and Ayush; pass/fail decided by Shourya with Sandeep's confirmation. All criteria must be true.

| # | Criterion | Status | What exists | What is left |
|---|---|---|---|---|
| 1 | Vinayak Brain dashboard is live in production | ✅ (confirm) | Frontend on Vercel (`vinayak-os.vercel.app`), backend on Railway, Supabase Postgres; CI on every push | Confirm Sandeep's company workspace is the one connected and synced in production; agree what "v1" means for the month-6 review (recommended: the Pulse landing page, not the current chart pages) |
| 2 | Sandeep has used the dashboard ≥ 4 days/week for 60 consecutive days | 🟡 | Supabase Auth sessions exist | **No usage tracking.** Add a `usage_events` table (user, workspace, first-seen-per-day), a per-user "active days" query, and a small admin view so the 60-day window is provable. The 60-day clock cannot start until this exists and Sandeep is onboarded as a daily user |
| 3 | AI chat answers a fixed 50-question evaluation set with ≥ 80% factual accuracy and 100% citation compliance | 🟡 | 29 golden cases; harness grades citation compliance (100% on the deterministic path), refusal, intent, bucket; CI ship-gate | Grow to **50 hand-verified questions**; add **expected values** to cases so *factual accuracy* is graded (today only intent/bucket/citation are); grade the **agent (native) path**, which is the production path, in CI; freeze the set with Shourya so "fixed" is auditable |
| 4 | Experiments log contains ≥ 30 logged experiments with outcomes captured | 🔴 | Nothing — no table, no UI | Build the **experiments log**: `experiments(hypothesis, source: ai_suggested \| manual, action_refs, metric, baseline, start, end, outcome, decided_by)`; a page to log and close experiments; the Strategy watcher that *suggests* experiments (dead-stock clearance, reorder nudge, credit hold, price test) from Pulse signals. 30 logged *with outcomes* means experiments must start months before the review |
| 5 | ~~Busy API integration live with ≥ 99% successful daily syncs over 30 days~~ | — | Dropped by agreement | — |
| 6 | Month-3 demo of the 90-day plan has passed; month-6 demo passes its defined criteria | 🟡 | No 90-day plan existed; `PLAN.md` now serves as it and proposes the month-3 (1 Dec 2026) and month-6 criteria | Agree the criteria in writing with Shourya; record the month-3 outcome here |

### What Milestone 1 needs that the current roadmap under-weights

The engineering roadmap (see `BIDE_STAGE_REVIEW.md` §7) is collections-first. Milestone 1 and the bonus criteria below add three things that must be sequenced in early, because two of them have long clocks:

1. **Usage tracking + Sandeep as a daily user** — the 60-day clock. Needs the Pulse/role-based home so there is a reason to open it daily, and the morning brief so the app comes to him.
2. **Experiments log + Strategy suggestions** — 30 logged experiments *with outcomes* implies ~5 per month starting now.
3. **Eval set to 50 with factual grading on the agent path** — a few days of engineering plus hand-verification time with Shourya.

## Half-yearly bonus criteria (context for prioritisation)

**H1 (month 6):** month-3 demo passed · wiki, experiments log and dashboard v1 live in production · AI prototype answers a 20-question set with ≥ 75% accuracy and 100% citation compliance · no critical production incidents in the prior 60 days.

- Wiki: 🔴 nothing in the repo. Recommended: a `docs/wiki/` (or the knowledge plane's rendered pages) covering business dictionary, data sources, decisions, and the per-company onboarding notes — the "you document — wiki, decisions, learnings" expectation.
- Incident log: 🔴 no incident tracking. Add `docs/INCIDENTS.md` (or a table) so "no critical incidents in 60 days" is evidenced, not asserted.

**H2 (month 12):** Milestone 1 achieved · AI chat in production use by Sandeep and Shourya · content engine has produced ≥ 40 published content pieces approved by Sandeep · Strategy mode live with ≥ 10 AI-suggested experiments executed.

- Content engine: 🔴 not started (Marketing field, `BIDE_BUILD_REFERENCE.md` §7 Marketing). Needs the knowledge plane for brand voice, a drafting tool, and an approval flow that records Sandeep's approval per piece.

## Milestone 2 — "The System Earns Its Keep" (target: end of month 12; latest month 14)

All of: Milestone 1 criteria still true · Vinayak annual revenue run-rate at month 12 ≥ ₹95 Cr · ≥ ₹12 Cr of active pipeline (RFQs + quotes + recently closed) credibly attributable to the system through **logged origination** in lead capture, follow-up, or AI suggestion features · Strategy mode has produced ≥ 30 experiment suggestions in the year, ≥ 15 acted on · content engine ≥ 80 published pieces approved by Sandeep.

Implications for the build: the **lead-capture hub and follow-up state machine** (Sales field) must carry an `origination` record on every lead, quote and deal from the day they ship, otherwise the ₹12 Cr attribution cannot be evidenced. Pipeline snapshots (`pipeline_daily_snapshot`) start recording history the same day.

## Milestone 3 — "EDHway Becomes Real" (target: end of month 24; latest month 30)

Any one of: (A) ≥ 1 paying external MSME using it for ≥ 6 months on a paid contract · (B) deployed across ≥ 3 sister companies with each company's CEO (or equivalent) active ≥ 4 days/week for 90 consecutive days · (C) a strategic event (funding, acquisition offer, spin-out, licensing).

Implication: Path B is the Vinayak group rollout already planned (`BIDE_BUILD_REFERENCE.md` §11) and is the most controllable — the same usage tracking built for Milestone 1 must work per company and per CEO from the start.

## Reporting cadence

Weekly 1:1 with Shourya; monthly review with Sandeep. Decision authority for Track 4 (AI brain layer, wiki, experiments log, content engine) sits with Ayush unless overridden by Shourya or Sandeep.
