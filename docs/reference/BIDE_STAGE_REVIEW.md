# BIDE Stage Review

> Product review, September 2026. Where the product stands against its own documents, what the finance vertical is missing, and how to rebuild the dashboard around decisions with an agent working in the background.

What the documents say we are building, where the code actually is against that, why the current dashboard reads as charts rather than answers, and how the same substrate becomes an owner's cockpit with an agent working behind it.

**Sources** The Business IDE (BIDE) reference · Build Manual · V0 Finance Spec · Tool Catalog · Analytical Handlers Catalog · Marketing Spec · Stagewise Business Plan · the `os-vinayak` codebase as of today

## 1 · Where the product is

The BIDE reference describes twelve layers and, separately, a five-stage go-to-market plan. Read against the code, the honest position is: **the substrate and the safe reasoning core are built; the "hands" have a first working finger; the brain has no pulse of its own yet.**

| Layer                     | Doc status       | Code today                                                                          | Gap                                                                         |
|---------------------------|------------------|-------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| 0–1 Foundations, identity | **Built**    | FastAPI + Next 16, Supabase Auth, BFF key now enforced, per-workspace scoping       | No roles; no "who may approve money"                                        |
| 2 Ingestion               | **Built**    | 10 TranzAct reports hourly, resumable cursor, content-hash upsert, Zoho provisional | Zoho unverified on a live org; no webhooks; sync-run attribution just fixed |
| 3 Canonical               | **Mostly**   | All panels read `canon_*`; 9 object families; `ingest_issues`                       | No GL, no AP aging, no entity resolution across sources                     |
| 4 Read & present          | **Built**    | 55 queries, 45 endpoints, 20 pages, 38 panels                                       | Descriptive only — the subject of §4                                        |
| 5 Memory                  | **Mostly**   | Profile, decaying facts, threads, multi-turn, entity summaries                      | No episodic log; correction-from-chat loop is manual                        |
| 6 Reasoning base          | **Built**    | Deterministic engine + safety spine + 29-case harness in CI                         | Agent path not ship-gated; no raw-dump baseline recorded                    |
| 7 Tools                   | **Partial**  | 38 read tools, 1 action tool                                                        | Memory/meta tools partly; no draft-PO, no credit-flag action                |
| 8 Agent core              | **Partial**  | Grounded tool-use loop is the default `/ask` path                                   | Only a question can trigger it                                              |
| 9 Action spine            | **Partial**  | Ledger → inbox → approve → send → retry, end to end                                 | One action; no tone ladder, promise-to-pay, recovery proof                  |
| 10 Workflows & synapses   | **Seeded**   | `events` table exists, `ar_daily_snapshot` accumulating                             | Nothing emits or consumes an event; no declarative workflows                |
| 11 Scale-out              | **To build** | —                                                                                   | —                                                                           |

Verdict

**Stage 0 is engineering-complete and commercially unstarted.** The plan's Stage-0 exit is "overdue → drafted → approved → sent → recorded on real data, tests pass including must-refuse, and one business on a paid trial". The first two are true in code today. Whether the third is true is not in any document.

Against the V0 Finance Spec's own wave plan: Wave 0 done, Wave 1 done, **Wave 1.5 (Pulse) not started**, Wave 2 (deep collections) about a third done, Wave 3 (credit synapse) has the verdict query but not the flag, the event, or the badge. That is exactly the gap you are feeling: the plan already prescribes the owner-facing layer, and it is the one part that hasn't been built.

## 2 · What we are building

Stripped of layer numbers, the documents agree on one product. BIDE is **a system of record that thinks**: it pulls a company's operating data out of the ERPs it is trapped in, normalises it into one model, answers with numbers it can cite and a confidence it computed, remembers what the owner teaches it, and takes actions that a human approves. Three promises organise everything — *Know* (what is happening), *Understand* (why), *Decide* (what to do) — and the claim is that raw-dumping the data into a chatbot fails on all three the moment a business is real and ongoing.

Two commitments in the reference matter more than the rest for the questions you are asking:

- **"The dashboard is the hook; the parser and memory are the moat."** The docs are explicit that the surface has had more effort than it deserves and that the correction is to build inward. This is right — but it has been read as "don't invest in the dashboard", when the actual instruction is "make the dashboard an output of the brain, not a separate product".
- **One loop, many triggers.** Trigger → Gather → Reason → Gate → Act → Remember. A chat question, a scheduled scan and an emitted event are supposed to be three entrances to the same loop. Today only the first entrance exists. The background agent you describe is not a new system; it is the other two doors.

Commercially the plan is narrower than the vision, on purpose: sell "see every rupee owed, chase the right customer at the right time, stop giving credit to defaulters" to TranzAct manufacturers; never say "AI brain" to a customer; prove one number (days-to-get-paid, before and after) and let that number sell the next account.

## 3 · What is lacking

### The surface answers "what", never "so what" — FIXED 2026-09-10

> Resolved in Sprint 1: Today (the Pulse) is the landing page and the business
> pages are now organised by where money is in its journey — Money in, Money out,
> Stock & making, Customers — each opening with a stage flow that shows what is
> stuck. Fourteen repetitive pages became four, with one home per fact.


Twenty pages and 38 panels, every one a faithful chart of a report. A revenue trend, an aging donut, a top-customers table. None of them carries a delta against the business's own normal, an attribution of what moved it, or a next step. An owner already knows roughly what he sold; what he opens the app for is *what changed, why, and what do I do about it before lunch*. The Analytical Handlers Catalog lists `why_changed`, `anomaly_scan`, `period_compare`, `business_pulse` as built handlers in the Ask engine — they exist as chat intents but never made it onto a screen.

### The agent only speaks when spoken to

Everything intelligent in the system is pull. No job runs the agent on a schedule, no detector emits an event, no worker consumes one, no episodic log records what the brain did. `ar_daily_snapshot` has been quietly recording AR history since migration 008 — the raw material for aging drift, inferred payment dates and DSO trend — and nothing reads it.

### One action, and no proof

`collections.draft_chase` is a flat two-tone reminder. The spec's tone ladder (R1–R4 by days overdue, per customer not per invoice, R4 drafted for the owner's own voice), promise-to-pay, chase pausing, escalation on broken promises, and — most importantly — **recovery stats** (₹ that came home within 14 days of a chase, DSO series annotated with go-live) are not built. Without the last one there is no "collected faster" number, and the business plan says that number is the sales deck.

### The finance vertical is capped by four missing inputs

No cost of goods (so no margin, no gross profit by customer or SKU — the catalog calls this the single biggest unlock). No payment receipt dates (DSO is a proxy; behaviour scoring is a proxy). No accounts payable aging (purchase invoices exist, vendor outstanding does not), so no DPO, no cash-conversion cycle, no true 30-day cash view. No bank or cash balance. Each of these is a data-acquisition problem, not a code problem, and §6 lays out the cheapest route to each.

### Trust harness is thinner than the docs imply

29 cases against a 50-case target; the native agent path is not graded in CI; no raw-dump baseline has been recorded; nothing yet evaluates *actions* ("must refuse to draft for a disputed customer") as opposed to answers. Roles and the money-approver are absent, so today any allowlisted user can approve a send.

### Memory captures less than it could

Facts enter through a form on the Business Brain page. The reference's capture loop — the owner corrects an answer in chat, the correction becomes a fact, the next answer changes — is not wired. `suggested_fact` exists on the Answer object but no UI acts on it. Every promise-to-pay, every "actually that customer is on 45-day terms", every rejected draft with a reason is a fact the system should be harvesting for free.

## 4 · The dashboard, rebuilt around decisions

The design rule: **a card earns a place on the home screen only if it names a delta, a cause, or a decision.** Anything that merely shows a number belongs one click down. Under this rule the current overview page becomes drill-down, and the home page becomes something closer to what a good CFO would put on one sheet for the owner every Monday.

### Three surfaces instead of twenty pages

- **Today (the Pulse).** Six to eight cards, sorted by severity, each with a headline figure, a change against the business's own baseline, one sentence of attribution, and one button that starts an action. This is the landing page. It is also, verbatim, the morning WhatsApp brief.
- **Inbox.** What the brain has prepared and is waiting for a person on: chase drafts, credit holds, reorder drafts, anomalies to acknowledge. Grouped by workflow, batch-approvable, each item showing the evidence it was built from and a "why" the owner can read in ten seconds.
- **Explore.** The existing pages, unchanged, reached from cards rather than from the sidebar as peers. They are good drill-downs; they are bad front doors.

### Anatomy of a card

Aging drift · last 30 days

₹18.4 L ↑ slid into 61–90 / 90+ 

8.1% of your receivables moved into the two worst buckets this month, almost all of it Dev Colour (₹11.2 L, 74 days) and Shree Shyam (₹4.9 L).

Draft chases (2)  Ask about this  Synced 2 h ago · **Certain**

Every card carries the same five things: the figure, the comparison ("vs your usual", never vs an arbitrary period), the attribution (top contributors by absolute contribution), the action, and the trust line (freshness plus the confidence label the safety spine already computes). Numbers are illustrative; the shape is the point.

### The first eight cards

These are the V0 Finance Spec's Pulse cards, unchanged in formula, plus two working-capital cards from the handlers catalog. Every one runs on data already synced.

| Card                   | The question it answers              | Source                                                                            | Action it offers                |
|------------------------|--------------------------------------|-----------------------------------------------------------------------------------|---------------------------------|
| Aging drift            | Is money sliding toward bad?         | `ar_daily_snapshot`, bucket totals today vs D-7/D-30                              | Draft chases for the movers     |
| Payment behaviour      | Who is getting slower?               | Composite score now; Δ avg days-to-pay once inferred payments exist               | Credit hold suggestion          |
| 30-day cash view       | What's coming in vs going out?       | AR by due date + 0.5 × overdue − open POs by expected date                        | Review the outflows             |
| What changed this week | Why is revenue up or down?           | 7-day Σ vs trailing 8-week mean; top 3 customers and SKUs by contribution         | Ask / nudge the missing regular |
| Reorder radar          | Which regulars are overdue to order? | Median inter-order gap; flag at 1.5×                                              | Draft nudge                     |
| Concentration trend    | Is dependence growing?               | Top-1 / top-3 share, 90d vs prior 90d                                             | —                               |
| Trapped capital        | Is dead stock growing?               | Dead-stock value now vs 30 days ago                                               | Season/stock push draft         |
| Anomalies              | Anything that shouldn't happen?      | Invoice \> 4× customer median · vendor price +25% · negative stock · stale report | Acknowledge / investigate       |
| Working capital        | Where is my cash locked?             | Inventory + AR − AP composition (AP once purchase due dates are mapped)           | —                               |
| Collections proof      | Is the chasing working?              | ₹ recovered within 14 days of a chase; DSO series with go-live marker             | Weekly one-pager                |

### One home, four readers

Owner, CFO, CA and sales head want different cards first, not different products. A role picks the default order and which cards are pinned; the underlying tools are identical.

**Owner / CEO**

- What changed this week and why
- 30-day cash view
- Top three risks (aging drift, concentration, a regular gone quiet)
- Decisions waiting in the Inbox

**CFO / finance manager**

- Working capital and its drift
- Aging drift and payment behaviour
- Cash view 30 / 60 / 90
- AP due and open PO commitments
- Collections proof

**CA / accountant**

- Anomalies and exceptions to clear
- Period pack: revenue two bases, AR, AP, inventory value, exports
- Data quality (`ingest_issues`) before sign-off
- GST readiness — blocked until a ledger source lands

**Sales head**

- Credit gate on every quote and order
- Reorder radar and win-back list
- Quote conversion and open pipeline
- Overdue orders customers are waiting on

### Two rules that keep it honest

First, **the comparison is always the business's own baseline** — its median order gap, its trailing eight weeks, its own aging history — because an SMB owner distrusts industry benchmarks and trusts his own past. Second, **the confidence label is on the card, not hidden in chat.** A card built on a proxy (payment behaviour before receipt dates exist) shows **Probable** and says what would make it certain. That is the reference's Family-D rule ("flagged is better than wrong") applied to the screen, and it is also the cheapest onboarding prompt you will ever ship: the card itself asks the owner for the missing data.

## 5 · The agent in the background

Nothing new is needed in the reasoning layer. What is needed is the two missing entrances to the loop — schedule and event — plus a record of what happened, and a gate that can earn autonomy over time.

**Trigger** Post-sync hook · daily 06:00 · Monday 08:00 · an event — watchers, not questions

**Gather** Same read tools, same evidence — company_id injected

**Reason** Deterministic detector first; model only to compose — numbers never from the model

**Gate**side-effect × quality × history → auto / confirm / human — money always human

**Act** Propose to the ledger; execute after approval — email, WhatsApp, flag, draft PO

**Remember** Episodic log + outcome — what was approved, edited, rejected, and what it recovered

### Watchers are rows, not code

A watcher is a declarative workflow: `{trigger, detector, gather_tools, compose_tool, gate_policy, cooldown}`, stored in a `workflows` table per workspace and switchable off by the owner. The detector is deterministic SQL over canonical data and emits a typed event with an idempotency key; the model is invited only when something has to be worded. This keeps the background agent inside the same guarantee as chat: it cannot originate a number, and every message it drafts passes the numeric guard before it reaches the inbox.

| Watcher        | Detector → event                                                | Composes                               | Gate                                         |
|----------------|-----------------------------------------------------------------|----------------------------------------|----------------------------------------------|
| Overdue rung   | Invoice crosses 3 / 15 / 30 / 60 days → `invoice.overdue{rung}` | Chase draft at that rung, per customer | Confirm; R4 drafted for the owner's own send |
| Promise broken | Promised date + 2 days, still unpaid → `promise.broken`         | Escalation +1, Pulse anomaly line      | Confirm                                      |
| Credit gate    | Verdict flips to STOP/CAUTION → `credit.flagged`                | Flag row; badge on Quotes and Orders   | Auto for the badge, human for a hold         |
| Reorder radar  | days_since_last \> 1.5 × median gap → `customer.quiet`          | Personal nudge listing usual items     | Confirm, batchable                           |
| Stock cover    | Days of cover \< threshold → `stock.low`                        | Draft PO to last vendor at last price  | Confirm; money-gated above a limit           |
| Data stale     | Report \> 25 h old → `data.stale`                               | Engineering alert; badge on every card | Auto                                         |
| Anomaly        | The four anomaly rules → `anomaly.found`                        | One-line note in Pulse                 | Auto (informational)                         |

### Runtime

One worker process (an APScheduler job now, a Celery worker when H3 lands) with three jobs. *After every canonical rebuild*: run all detectors for that workspace, emit events. *Every minute*: consume pending events, run the matching watcher through the `AgentRunner` with a trigger context instead of a question, write a `brain_runs` row (trigger, tools, evidence ids, gate decision, action id, outcome), propose to the ledger, notify. *Daily 06:00 IST*: assemble the Pulse cards, phrase them under the numeric guard, send the brief to the owner on WhatsApp or email, with each line deep-linking to its card. The Monday run also drafts the weekly one-pager.

### Earning autonomy without ever automating money

The reference's gate is CERTAIN → run, PROBABLE → confirm, UNCERTAIN → escalate. The missing piece is *history* as an input. Track, per workspace and per watcher, approvals without edit, approvals with edit, and rejections. A watcher whose last N proposals were approved unedited is eligible to graduate one rung — R1 reminders to trusted customers going out automatically after a 24-hour hold the owner can cancel — and any rejection demotes it. Sends have hard caps (one message per customer per seven days, no sends on disputed or promised accounts). Money and regulator actions never graduate; that stays a promise you advertise.

### Execution after approval

Today: email via Resend/SMTP. Next: WhatsApp Business API (start the DLT paperwork now; it is a multi-week lead). Then write-back where the source allows it — Zoho Books has a real API for payments, contacts and invoices; TranzAct is read-only until proven otherwise — so a promise-to-pay, a credit hold or a draft PO can land back in the system of record rather than only in ours. Every execution writes its result to the ledger and its outcome, later, to memory: which tone worked for which customer, how many days after a chase money arrived. That is the learning loop the reference calls "proactive memory", and it is what makes month six better than month one.

## 6 · Data that unlocks the rest

The finance vertical will plateau as a receivables product unless four inputs arrive. None needs a new adapter first; all can start as an accountant's upload and become an integration later.

| Input                 | Cheapest route now                                                                                                         | Unlocks                                                                   |
|-----------------------|----------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| Cost per SKU          | One CSV from the costing sheet; store as `memory_fact` per item with a validity date; Zoho `purchase_rate` where connected | Margin, gross profit by customer and product, price realisation, GMROI    |
| Payment receipt dates | Infer from `ar_daily_snapshot` (present on D, gone on D+1) — already accumulating; Zoho payments for exact dates           | True DSO trend, behaviour scoring, recovery proof                         |
| AP aging              | Purchase invoices already carry due dates: map vendor outstanding into a `canon_ap_flat` view                              | DPO, cash-conversion cycle, real 30-day cash view, 3-way match later      |
| Customer contacts     | Accountant task, 30 minutes; CSV import screen; auto-fill from Zoho contacts                                               | Every send. This is the single hard prerequisite the marketing spec names |

GST, bank feeds and GL stay a Stage-2 decision driven by which customers pay for them; the catalog is right that a ledger source (Busy, Tally, Zoho GL) unlocks eight deep-finance workflows at once.

## 7 · Sequence

Ordered by dependency and by what proves the product to a paying owner soonest. Each step is small because the substrate is done; most of this is query functions, one worker, and screens.

1.
    **History and the Pulse** (≈ 2 weeks)  
    The eight Pulse query functions and cards, registered as read tools; inferred payments from the snapshot table; `/pulse` as the landing page; the existing overview demoted to Explore. Nothing new to sync.

2.
    **Events, worker, episodic log** (≈ 2 weeks)  
    Detectors emit; a worker consumes; `brain_runs` records every loop; the first three watchers (overdue rung, data stale, anomaly). The daily WhatsApp/email brief ships here because it is just the Pulse phrased.

3.
    **Collections, properly** (≈ 2 weeks)  
    Tone ladder, per-customer drafts, promise-to-pay as a fact, chase pausing and escalation, recovery stats and the weekly one-pager. Contacts import screen. This is where "collected faster" becomes a number you can show.

4.
    **Credit synapse into Sales** (≈ 1 week)  
    `customer_flags`, badge on Quotes and Orders, hold proposal in the Inbox. The first cross-field flow, exactly as the reference wants it proven.

5.
    **Roles, autonomy ladder, action evals** (≈ 1–2 weeks)  
    Owner / approver / viewer; the graduation rule with caps; "must refuse to act" cases and the native runner in CI; record the raw-dump baseline.

6.
    **Reorder and stock watchers, draft PO** (≈ 2 weeks)  
    Reorder radar and stock-cover watchers with their drafts; cost-per-SKU upload; margin cards appear the day costs exist.

Roughly ten to twelve weeks to a product where the owner opens one page in the morning, sees what moved and why, approves what the system prepared, and can point to the money it brought home — with every number still traceable. That is the Stage-1 product the business plan describes, and it is built entirely on what is already in the repository.

Layer statuses are read from the code at the time of writing; formulas are quoted from `docs/V0_FINANCE_SPEC.md` and `docs/ANALYTICAL_HANDLERS_CATALOG.md`. Figures in the card mock are illustrative.
