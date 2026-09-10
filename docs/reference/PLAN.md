# BIDE Milestone Plan

> Delivery plan, September 2026. Week-by-week plan to hit Milestones 1, 2 and 3 as early as possible, ordered by the criteria that have clocks. Also serves as the 90-day plan, with the month-3 and month-6 demo criteria proposed for agreement with Shourya. Week 1 = Monday 1 Sep 2026 (agreed start date); month-3 demo 1 Dec 2026; Milestone 1 review 1 Mar 2027.

# BIDE Milestone Plan

A week-by-week plan to hit Milestone 1 by month 6, Milestone 2 by month 12 and Milestone 3 by month 24 — ordered by which criteria have clocks, not by which are most interesting to build. This document also serves as the 90-day plan the offer letter refers to, with the month-3 and month-6 demo criteria proposed here for agreement with Shourya.

## 1 · Dates and assumptions

**Week 1 = Monday 1 September 2026**, the agreed start date; month *N* ends on the 1st of the corresponding month, so the month-3 demo is 1 December 2026 and the Milestone 1 review is 1 March 2027. Today is week 2: Sprint 0 is already in progress. One engineer, 50–55 hours a week, with Shourya reviewing weekly and Sandeep monthly. The Busy integration is dropped. Everything is built on the current repository — nothing here is a rewrite.

- **1 Sep 2026** — Week 1. Start. Sprint 0 begins.
- **30 Nov 2026** — Month 3 — 90-day demo. Gate. Criteria in §4.
- **by 31 Dec 2026** — 60-day usage clock must have started. Sandeep on the daily habit; usage tracking live.
- **1 Mar 2027** — Month 6 — Milestone 1 review. All six criteria; H1 bonus criteria.
- **1 May 2027** — Month 8 — latest acceptable M1. Grant reduces after month 6; forfeited after month 8.
- **1 Sep 2027** — Month 12 — Milestone 2 review. Revenue, attributable pipeline, experiments, content; H2 bonus.
- **1 Sep 2028** — Month 24 — Milestone 3 review. Path B: three sister companies, CEOs daily for 90 days.

## 2 · The four clocks

Four Milestone-1 criteria cannot be crammed at the end. They decide the order of everything else.

| Clock                                                         | Why it's a clock                                                                                                   | Must be live by                          | Which means building first                                                                                               |
|---------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------|------------------------------------------|--------------------------------------------------------------------------------------------------------------------------|
| Sandeep: ≥ 4 days/week for 60 consecutive days                | 60 days must end before 1 Mar; the habit takes time to form; a missed week restarts the count                      | 29 Dec 2026 (latest); aim 17 Nov 2026    | Usage tracking; a home page worth opening daily (Pulse); the brief that brings him to it; his role's layout              |
| ≥ 30 experiments logged *with outcomes*                       | An experiment needs 2–4 weeks to have an outcome; 30 with outcomes by 1 Mar means ~6 started a month from November | Log live 1 Oct; first suggestions 18 Oct | Experiments table + page; Strategy suggestions from Pulse signals; the rule that every Inbox action can be an experiment |
| 50-question set, ≥ 80% factual, 100% citation                 | Hand-verifying 50 answers with Shourya takes calendar time, and the set must be frozen weeks before the review     | Frozen 1 Jan; passing 1 Feb              | Expected-value grading in the harness; the agent path in CI; question collection from real Ask usage                     |
| No critical incident in the 60 days before month 6 (H1 bonus) | Anything risky must ship before 1 Jan                                                                              | Feature freeze 1 Jan                     | Incident log; the worker split and watchers land in Nov–Dec, not Feb                                                     |

The consequence: **by the month-3 demo (30 Nov) the product Sandeep will use every day must already exist**, and he must already be using it. Months 4–6 are for the eval set, experiments accumulating, hardening, and starting Milestone 2's long-lead work — not for the core product.

## 3 · Months 1–6: Milestone 1

Two-week sprints. Each sprint names what ships to production, which milestone criterion it serves, and the evidence it leaves behind. Everything marked \*\*exists\*\* is already in the repository and only needs wiring or finishing.

### Sprint 0 · Weeks 1–2 (1–12 Sep) — make the milestones measurable

| Ship                                                                                                                                                                        | Serves             | Notes                                                                                  |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------|----------------------------------------------------------------------------------------|
| Deploy the fixes already in the working tree (sync-run attribution, BFF key, retry-send, dead code); run migration 019 on production                                        | Stability          | Commit, deploy, verify Sync page shows per-company runs                                |
| `usage_events` table + middleware that records one row per user per workspace per day on any authenticated request; `active_days(user, window)` query                       | M1-2               | Tiny; must exist before anyone's 60 days can count                                     |
| `experiments` table + a plain page to create, update and close an experiment (hypothesis, source, metric, baseline, start, end, outcome, decided by)                        | M1-4, H2, M2       | v0 is a form; suggestions come in Sprint 2                                             |
| Milestone tracking: the evidence tables (usage, experiments, incidents, eval runs) plus `python -m vinayak.scripts.milestone_status` | All | The tracker is `docs/reference/MILESTONES.md`; the CLI prints the countable half to paste in (a board screen was built first and removed — a review is a conversation, not a page) |
| `docs/INCIDENTS.md` with a definition of "critical"; `docs/wiki/` skeleton (business dictionary, data sources, decisions log, per-company notes)                            | H1                 | Wiki content accrues every sprint from then on                                         |
| Onboarding asks role (runs the company / accounts / CA / sales) and the two approval permissions; `users.role` actually read; role seeds card layout                        | M1-2               | Layout data model only; Pulse cards arrive next sprint                                 |
| Start WhatsApp Business API + DLT registration paperwork                                                                                                                    | Brief, collections | 2–4 week lead; costs nothing to start now                                              |

### Sprint 1 · Weeks 3–4 (15 Sep–26 Sep) — the page worth opening every morning

| Ship                                                                                                                                                                                                      | Serves      | Notes                                                                                             |
|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------|---------------------------------------------------------------------------------------------------|
| Pulse v1: aging drift, payment behaviour (v1 proxy), 30-day cash view, what changed this week, reorder radar, concentration trend, trapped capital, anomalies — as query functions, cards, and read tools | M1-1, M1-2  | Formulas are already specified in `V0_FINANCE_SPEC.md`; `ar_daily_snapshot` has been accumulating |
| Inferred payments from the AR snapshot → days-to-pay per invoice and customer                                                                                                                             | Pulse, eval | Unlocks real DSO trend and behaviour v2 later                                                     |
| `/pulse` becomes the landing page; role-ordered cards; existing pages move under Explore                                                                                                                  | M1-2        | Every card: figure · vs usual · why · action · freshness · confidence                             |
| Daily brief by email at 06:00 IST: the Pulse phrased under the numeric guard, each line deep-linked                                                                                                       | M1-2        | WhatsApp follows when DLT clears                                                                  |

### Sprint 2 · Weeks 5–6 (29 Sep–10 Oct) — the brain runs on its own; experiments begin — **SHIPPED 10 Sep**

Shipped ahead of the window. `vinayak/brain/` holds the runtime: `bus.py`
(the events table with a dedupe key), `detectors.py` (the three watchers),
`consumer.py` (events → proposals in the Inbox), `strategy.py` (the weekly
suggestions), `metrics.py` + `outcomes.py` (how an experiment is judged and
closed), `runner.py` (every pass inside a `brain_runs` episode). The worker is
a separate process (`python -m vinayak.worker`). Migration 021 adds `workflows`,
`brain_runs`, the event dedupe index and the experiment window fields. Verified
end to end against a seeded Postgres: six watchers run, five rungs detected, four
chases proposed, six experiments suggested, a second pass emits nothing, and an
experiment accepted, started and closed with a computed outcome.

| Ship                                                                                                                                                                                                                                                                                              | Serves       | Notes                                                                                       |
|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|--------------|---------------------------------------------------------------------------------------------|
| Worker split (separate Railway service, Celery + Redis or APScheduler in its own process); `events` emission from three detectors (overdue rung, data stale, anomaly); event consumer; `brain_runs` episodic log; `workflows` table                                                               | M1-1         | The architecture's Layer 10, first real use                                                 |
| Strategy suggestions v1: a weekly watcher that turns Pulse signals into *proposed experiments* (clear this dead stock to these customers; hold credit on X; nudge these six regulars; test firm tone on late payers) and files them in the experiments log as `ai_suggested`, awaiting acceptance | M1-4, H2, M2 | Aim for 4–6 suggestions a week; Sandeep or Shourya accepts, the log tracks outcome          |
| Every Inbox approval can be tagged "run as experiment" with a metric and window; outcome computed from snapshots                                                                                                                                                                                  | M1-4         | Turns ordinary chases and nudges into logged experiments with outcomes for free             |
| **Onboard Sandeep as the daily user**: his workspace, his role, the brief to his inbox; walk him through Pulse and the Inbox once in person                                                                                                                                                       | M1-2         | Target first active day ≤ 18 Oct; 60-day clock target 18 Oct–17 Dec, with January as buffer |

### Sprint 3 · Weeks 7–8 (13 Oct–24 Oct) — collections done properly

| Ship                                                                                                                                                                          | Serves               | Notes                                                                             |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------|-----------------------------------------------------------------------------------|
| Tone ladder R1–R4 per customer; promise-to-pay as a fact with chase pausing and `promise.broken`; dispute flag; chase list v2 (priority = outstanding × lateness × behaviour) | M1-1, experiments    | Extends the existing `collections.draft_chase` and Inbox                          |
| Recovery stats: ₹ recovered within 14 days of a chase; DSO series with go-live marker; Collections-proof card and the Monday one-pager                                        | M1-1, M2 attribution | The number that proves value; also the outcome metric for collections experiments |
| Contacts CSV import screen; Zoho contacts auto-fill where connected                                                                                                           | Sends                | Accountant task, 30 minutes                                                       |
| Eval: add expected values to the 29 cases; harness grades factual accuracy; `--runner native` in CI as a second gate                                                          | M1-3                 | Question collection starts from real Ask logs from Sprint 1 onward                |

### Sprint 4 · Weeks 9–10 (27 Oct–7 Nov) — first synapse, group view, eval growth

| Ship                                                                                                                                  | Serves     | Notes                                                                             |
|---------------------------------------------------------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------|
| Credit synapse: `credit.flagged` → `customer_flags` → badge on Quotes and Orders → hold proposal in the Inbox                         | M1-1, demo | Accounts → Sales, the reference's first synapse                                   |
| Group view v1: one row per connected company (cash view, overdue, drift, what changed, Inbox count); second Vinayak company connected | M1-1, M3   | Sandeep sees the group, not one company — the reason a group owner opens it daily |
| Eval set to 50 candidate questions drawn from real usage; hand-verification sessions with Shourya begin                               | M1-3       | Two sessions of an hour each                                                      |
| Wiki: decisions log and business dictionary filled from the reference docs; per-company onboarding notes                              | H1         |                                                                                   |

### Sprint 5 · Weeks 11–12 (10 Nov–21 Nov) — harden, then demo

| Ship                                                                                                                                   | Serves                      | Notes                                                               |
|----------------------------------------------------------------------------------------------------------------------------------------|-----------------------------|---------------------------------------------------------------------|
| Reorder-radar and win-back nudges as watchers with drafts (Marketing engines 1–2), with the 20% hold-back recorded per campaign        | M2 attribution, experiments | Every nudge is an experiment with a measurable outcome              |
| Structured logging with request and company ids; alerting on failed syncs and watcher errors; Sync page shows worker and bridge health | H1 incidents                | Nothing shipped in the freeze window should be able to surprise you |
| WhatsApp brief and sends if DLT has cleared                                                                                            | M1-2                        | Email remains the fallback                                          |
| Demo rehearsal with Shourya on real data; fix what it shows                                                                            | Demo                        |                                                                     |

### Week 13 (24–30 Nov) — month-3 demo

Criteria in §4. The demo is Sandeep's own Pulse and Inbox on his own numbers, not slides.

### Sprints 6–11 · Months 4–6 (1 Dec–1 Mar) — let the clocks run; start Milestone 2's long leads

| Weeks | Ship                                                                                                                                                                                                                                                                                 | Serves                                              |
|-------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------|
| 14–15 | Eval set frozen at 50 with Shourya's sign-off; agent path passing ≥ 80%; both paths gated in CI. Feature freeze on anything touching the request path from 1 Jan.                                                                                                                    | M1-3, H1                                            |
| 14–17 | Lead capture hub v1: web form + WhatsApp inbound + manual entry → `canon_lead` with **origination** recorded on every lead; the follow-up state machine (day 2/5/10; no closed-lost without three touches); quote drafts linked to leads; `pipeline_daily_snapshot` starts recording | M2 (₹12 Cr attribution has to accumulate from here) |
| 16–19 | Content engine v1: brand voice and product facts in the knowledge plane (pgvector); drafting tool; approval flow that records Sandeep's approval per piece; publish log. Target: 2 approved pieces a week from week 20                                                               | H2 (40), M2 (80)                                    |
| 18–21 | Stock-cover watcher and draft PO (money-gated); cost-per-SKU upload; margin cards appear the day costs exist; experiments keep flowing from Strategy suggestions                                                                                                                     | M1-4, experiments                                   |
| 20–24 | Tally bridge v1 for the first Tally-running sister company (pull only); third company connected; entity resolution across the group                                                                                                                                                  | M3 Path B                                           |
| 22–25 | Milestone-1 evidence pack assembled from `MILESTONES.md` and the status CLI: usage report, experiments export with outcomes, eval run output, incident log, demo record                                                                                                                             | M1 review                                           |
| 26    | **Month-6 review** (week of 1 Mar 2027)                                                                                                                                                                                                                                              | M1                                                  |

## 4 · The month-3 demo — proposed criteria

The offer letter refers to "the month-3 demo of the 90-day plan" without defining either. These are proposed for agreement with Shourya in week 1, so the gate is written down before it is judged. All must be shown live, on Sandeep's real data, in production.

- Sandeep opens the app and lands on a Pulse that says what changed this week and why, in his role's order, with freshness and confidence on every card.
- The morning brief has arrived in his inbox (or WhatsApp) every working day for the preceding 30 days and each line opens the right card.
- At least three watchers are running unattended (overdue rungs, anomalies, data stale) and have produced items in the Inbox; at least ten actions have been approved and executed, and the ledger shows every one with its evidence.
- The collections proof card shows recovery against chases sent, with every rupee traceable.
- The credit gate shows on Quotes and Orders for at least one flagged customer.
- The experiments log holds at least ten experiments, at least five with outcomes, at least half of them AI-suggested.
- Usage tracking shows Sandeep active on at least 4 days in each of the previous 4 weeks (the 60-day clock is already running).
- The eval harness passes in CI on both paths at 100% citation compliance on at least 40 questions.
- No critical incident in the previous 30 days; `docs/INCIDENTS.md` and the wiki exist and are current.

## 5 · The month-6 review — what "pass" looks like

| Criterion                                                                                            | Evidence (status CLI + MILESTONES.md)                              | Target on 1 Mar 2027                                                                                                                       |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------|
| Dashboard live in production                                                                         | Deployment record; Pulse, Inbox, group view screenshots on the day | Live since October                                                                                                                         |
| Sandeep ≥ 4 days/week for 60 consecutive days                                                        | `usage_events` active-days chart per week                          | A completed 60-day window ending before 1 Mar (planned 18 Oct–17 Dec, with a second window as backup)                                      |
| 50-question set, ≥ 80% factual, 100% citation                                                        | Harness output from CI on the frozen set, both paths               | ≥ 40/50 correct, 100% cited, on the native (production) path                                                                               |
| ≥ 30 experiments with outcomes                                                                       | Experiments export                                                 | ≥ 30 closed with a recorded outcome; ≥ 45 logged                                                                                           |
| Month-3 demo passed; month-6 demo criteria                                                           | Demo records                                                       | Month-6 demo = the month-3 criteria plus: group view with ≥ 2 companies; first synapse live; content engine and lead hub in production use |
| H1: wiki, experiments log, dashboard v1 live; 20-question set ≥ 75%; no critical incident in 60 days | Wiki index; incident log                                           | Subsumed by the above; incident-free window 1 Jan–1 Mar                                                                                    |

## 6 · Months 7–12: Milestone 2 — the system earns its keep

Milestone 2 is mostly about accumulation, so the machinery must be running by month 7 and the second half is about scale and evidence.

| Months | Work                                                                                                                                                                                                              | Criterion                                         |
|--------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------|
| 7–8    | Lead hub at full use: IndiaMART BuyLead parsing, instant acknowledgement, quotation generator from the price master; every lead, quote and deal carries origination; attributable-pipeline card on the group view | ₹12 Cr attributable pipeline                      |
| 7–12   | Strategy suggestions at a steady ~3/week with the acceptance rate tracked; suggestions broaden to pricing tests, vendor consolidation, cross-sell pairs, season pushes                                            | ≥ 30 suggestions, ≥ 15 acted on                   |
| 7–12   | Content engine at 2 approved pieces/week; catalogue and case-study pieces from real data; publishing to site and GBP                                                                                              | ≥ 80 approved pieces                              |
| 8–9    | Marketing engines 3–4 (cross-sell, stock and season push) with hold-back proof; monthly incremental-revenue report                                                                                                | Revenue attribution; discretionary bonus evidence |
| 9–10   | Tally write-back via the bridge (quotes, orders, promises); companies 2 and 3 in daily use; roles and approver fully enforced                                                                                     | M3 Path B groundwork                              |
| 10–12  | Hardening: connection pooler, Redis cache for Pulse and KPIs, per-tenant model budgets; M1 criteria re-verified (no degradation); M2 evidence pack                                                                | M2 review                                         |

The ₹95 Cr run-rate is outside engineering's control; what is in its control is that the attribution is *logged*, not argued — every lead source, every follow-up touch, every AI suggestion that led to a deal, from month 4 onward.

## 7 · Months 13–24: Milestone 3 — Path B

Path B (three sister companies with their CEOs active four days a week for 90 consecutive days) is the most controllable path and is already the rollout plan. Months 13–15: companies 2 and 3 fully onboarded with their own Pulse, brief and Inbox, and their CEOs' usage tracked from day one. Months 15–18: the 90-day windows run; a fourth company as backup. Months 18–24: the remaining companies, cross-company entity resolution and intercompany netting, the ERP-engagement stage for the first company, and — only if a prospect appears — one external pilot for Path A. The month-24 review then has three completed 90-day windows recorded in `MILESTONES.md`.

## 8 · Operating rhythm

- **Monday:** the sprint's shipping list; the four clocks in `MILESTONES.md` checked first.
- **Friday:** a fifteen-minute live demo to Shourya on production data; the weekly 1:1 is this demo plus the risk list — nothing is reported that cannot be shown.
- **Monthly:** `MILESTONES.md` walked with Sandeep, refreshed from the status CLI that morning; his own usage and experiment numbers are in it, which is itself a nudge.
- **Every sprint:** wiki updated (decisions, data notes, onboarding notes); eval cases added for anything new; `INCIDENTS.md` reviewed; the plan re-dated if anything slipped — flagged early, as the letter asks.
- **Freeze discipline:** from 1 Jan to 1 Mar only fixes and content ship on the request path; new watchers ship disabled and are enabled per workspace after their eval cases pass.

## 9 · What would make this slip

| Risk                                                           | Effect                                            | Mitigation built into the plan                                                                                                                                             |
|----------------------------------------------------------------|---------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Sandeep doesn't form the daily habit                           | M1-2 fails regardless of engineering              | Brief comes to him; group view gives a group owner a reason; his numbers read out monthly; two possible 60-day windows before 1 Mar; ask Shourya to co-own the habit |
| Experiments logged but without outcomes                        | M1-4 counts only outcomes                         | Start by 18 Oct; short windows (2–4 weeks) with snapshot-computed metrics; every approved action can be an experiment                                                      |
| Eval set disputed at the review ("that answer is wrong")       | M1-3 argued instead of measured                   | Frozen set signed off by Shourya in January; expected values hand-verified against TranzAct reports; harness output archived per run                                       |
| A late feature causes a critical incident in the freeze window | H1 bonus lost                                     | Worker and watchers land in Oct–Nov; freeze from 1 Jan; incident definition agreed up front                                                                                |
| WhatsApp DLT delays                                            | Brief and sends on email only                     | Started week 1; email is a full fallback                                                                                                                                   |
| Solo capacity: too many parallel tracks in months 4–6          | Lead hub or content engine slips into M2's window | Order fixed: eval and freeze first, lead hub second (attribution clock), content third, Tally fourth; anything else waits                                                  |
| Start date shifts                                              | Every date moves                                  | All dates are relative to Week 1; `vinayak/milestones.py` computes them from the agreed start                                                                                  |

Week 1 = Monday 1 Sep 2026 (the agreed start date). Criteria for the month-3 and month-6 demos are proposals to be agreed in writing with Shourya in week 1. Milestone criteria are as stated in the offer letter, with the Busy integration dropped by agreement.
