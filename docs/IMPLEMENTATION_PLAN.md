# Implementation Plan — deterministic-first, every application and functionality per stage

> **SUPERSEDED** by the milestone-aligned master plan at the repo root:
> `IMPLEMENTATION.md`. Kept for the per-stage detail (endpoints, components,
> tests) which the master references. Stage numbering maps to master phases:
> Stage 1→A2, Stage 2→B, Stage 3→B, Stage 4→C, Stage 5→C/E, Stage 6→E.

> The build order agreed July 2026: ship every revenue-proving workflow on the
> proven pattern (cron + SQL + formula + template + human gate) FIRST; the
> agent/tool-calling upgrade to Ask comes after, plugging into the same registry.
> Supersedes the wave table in `V0_FINANCE_SPEC.md` §5.
> Formulas live in `V0_FINANCE_SPEC.md` (finance) and `MARKETING_SPEC.md`
> (engines) — this plan references, never restates.
>
> Effort assumes one full-time developer (Ayush). Stages are strictly sequential
> unless marked ∥ (parallel-safe).

---

## Stage 0 — Foundation ✅ DONE (recap only)

DB: `ar_daily_snapshot` (recording daily), `events`, `actions` · Tools substrate:
`vinayak/tools/` contract + registry + executor (writes only ever PROPOSE; money
gates to human; idempotency) · Zoho adapter scaffold (`/zoho/*`, `zb_*` tables,
hourly job) · CI: 61 tests + eval ship-gate · security hardening · multi-turn Ask.

**Carry-over ops items (do during Stage 1):** deploy latest to production
(snapshot hook goes hourly); confirm `JWT_SECRET`/`INTERNAL_API_KEY` in prod env;
ask accounts team about the post-July-2 invoice gap.

---

## Stage 1 — Pulse: the dashboard that talks (1.5 weeks)

*The owner's first screen becomes insight, not tables. Everything read-only.*

### Backend (`vinayak/schema/queries.py` + new `vinayak/schema/pulse.py`)
8 new query functions (formulas: `V0_FINANCE_SPEC.md` §2):
`get_aging_drift` · `get_payment_behaviour` (v1 proxy) · `get_cash_30d` ·
`get_week_delta` · `get_reorder_status` · `get_concentration_trend` ·
`get_dead_stock_delta` · `get_anomalies`.
Each returns `{headline, value, delta, severity, sentence, drill_link}` +
evidence list (so each doubles as a future read tool unchanged).

### API
`GET /dashboard/pulse` — all cards, severity-sorted, with freshness meta.
(One endpoint; cards computed live — no caching until slow.)

### Frontend (`apps/web`)
- `/w/[workspace]/dashboard/pulse/page.tsx` — card grid, severity order,
  each card: number · change chip · one-sentence "why it matters" ·
  "Ask about this" (prefills Ask) · drill link to the relevant panel.
- Make Pulse the default landing page after login.
- "history building — ready in N days" state for P1/P2-v2 cards.

### Jobs
None new (cards compute on request; `ar_daily_snapshot` already accumulating).

### Tests / acceptance
Unit tests per formula (fixed fixtures: drift math, median-gap cadence, week-delta
attribution, anomaly thresholds). **Accept when:** all 8 cards render on live
kbrushes data; P5 shows the 6 overdue-to-order regulars; a wrong-by-inspection
number on any card blocks the stage.

---

## Stage 2 — Collections: the first action (2 weeks)

*Detect → rank → draft → approve → send → prove. Entirely deterministic;
LLM only polishes prose behind the numeric guard.*

### DB (migration 010)
`customer_contacts` (also used by Stage 4 — build once here):
`(company_id, customer_code, contact_name, role, email, whatsapp, consent, PK(company_id, customer_code))`.

### Backend
- `vinayak/schema/queries.py`: `get_chase_list` (priority formula §3.1),
  `get_invoice_details`, `get_recovery_stats` (§3.5).
- `vinayak/workflows/collections.py` (new package `vinayak/workflows/`):
  - `scan()` — daily job: chase candidates per rung (§3.2 ladder), guardrail
    filters (consent, 14-day cap via ledger, promise-pause), builds drafts.
  - `build_draft(customer, rung)` — template + invoice facts; optional
    `llm.phrase`-style polish; **numeric guard runs on every draft**.
  - Proposes via `tools.executor` → `actions` ledger (`gate='confirm'`).
- `vinayak/notify/email.py` — SMTP/Resend sender, called ONLY by the
  approval-execution path, never by scan. Env: `SMTP_URL` or `RESEND_API_KEY`.
- Promise-to-pay: `memory.save_fact(promise_to_pay)` + broken-promise check in
  the daily scan (emits `promise.broken` event row).

### API
- `GET /actions/inbox` (pending, with drafts) · `POST /actions/{id}/approve`
  (executes send, logs result) · `POST /actions/{id}/reject` ·
  `POST /actions/{id}/edit` (owner's text wins, guard re-runs).
- `GET /dashboard/collections` — chase list + recovery stats.
- `POST /contacts/import` (CSV) · `GET/PUT /contacts` (the capture screen).

### Frontend
- **Approval Inbox** `/w/.../inbox`: pending drafts grouped by customer, full
  email preview, Approve / Edit / Reject, promise-to-pay quick-log
  ("promised ₹X by DATE"), badge count in nav.
- **Collections panel** on AR page: chase list with priority + rung.
- **Recovery card** on Pulse: DSO trend + ₹ recovered (go-live annotated).
- **Contacts screen** in Settings: 34-row editable list + CSV import +
  "missing contact" nag count.

### Jobs
`collections_scan` daily 07:00 IST (after AR sync) · `recovery_stats` nightly.

### Tests / acceptance
Rung selection · guardrail exclusions (no-consent, capped, promised) · draft
numeric-guard block on invented ₹ · idempotency (same customer+rung twice) ·
inbox API auth. **Accept when:** real overdue invoice → draft → owner approves in
UI → email delivered → invoice paid (or promise logged) → recovery card moves.
Eval additions: "must refuse to draft" cases.

### Owner-side prerequisites
Contact capture (30 min) · an email-sending domain (Resend setup, ~1 hr).

---

## Stage 3 — Credit gate: the first synapse (1 week)

*One event, three surfaces, no human relay — the "one brain" demo.*

### DB (migration 011)
`customer_flags (company_id, customer_code, flag, reason JSONB, set_at, cleared_at)`.

### Backend
- `check_customer_credit(conn, company_id, customer)` — deterministic verdict
  (§3.6: STOP / CAUTION / OK + reasons). Plain function AND registered read tool.
- AR sync post-step: rung-crossing detection → `events` rows (`invoice.overdue`).
- `vinayak/workflows/credit_gate.py` — event consumer (poll loop in scheduler,
  minutely): overdue event → verdict → upsert `customer_flags` → in-app notify;
  auto-clear when condition clears.

### API
`GET /dashboard/credit/{customer_code}` (verdict) · flags included in existing
quotes/orders/customers panel responses.

### Frontend
Credit badge (red STOP / amber CAUTION) on Quotes, Orders, Customers pages with
reason tooltip ("₹4.6L overdue, oldest 64 days") · Pulse anomaly line for new flags.

### Tests / acceptance
Verdict boundaries · event idempotency (one event per invoice per rung) ·
flag auto-clear. **Accept when:** invoice crosses overdue in a sync → badge
appears on the quote screen with zero human involvement. (Demo: pitch-deck slide 7 made real.)

---

## Stage 4 — Marketing engines 1+2: provable revenue (2 weeks)

*Reorder Radar + Win-Back on email, with holdout attribution. Formulas: `MARKETING_SPEC.md`.*

### DB (migration 012)
`campaigns` + `campaign_targets` (spec §3 tables).

### Backend
- `vinayak/schema/marketing.py`: `get_reorder_due` (E1), `get_lapsed_customers`
  (E2), cadence math shared with Pulse P5.
- `vinayak/workflows/campaigns.py`:
  `create_campaign(engine)` — audience build → guardrails (credit-STOP exclusion
  via Stage 3 verdict, 14-day cap, consent) → stratified 80/20 holdout split →
  per-target drafts → ledger proposals (batch-linked).
  `attribute()` — nightly: orders within 21d window per arm; incremental math.
- Templates per engine/rung; incentive slot fillable only from request payload
  (owner-typed), never generated.

### API
`POST /campaigns` (engine, template, holdout%) · `GET /campaigns` + `/campaigns/{id}`
(targets, arms, results) · batch endpoints on the inbox: `POST /actions/approve-batch`.

### Frontend
- **Campaigns page** `/w/.../campaigns`: engine picker → audience preview (with
  excluded-and-why list + missing-contacts count) → template edit → launch.
- Inbox batch mode (approve all / per-message edit).
- **Results card**: raw vs incremental ₹, response counts, per-campaign and
  cumulative "revenue we caused".

### Jobs
`campaign_attribution` nightly · engine scans weekly (E2) / daily (E1 — shares
the collections scan slot).

### Tests / acceptance
Holdout stratification & minimum-size skip · exclusion rules (STOP, capped,
no-consent, holdout never messaged) · attribution window math · incentive slot
cannot be model-filled. **Accept when:** one real reorder campaign runs
end-to-end and the results card shows arms compared after 21 days.

### Owner-side
Approve first campaign · decide incentive policy · (start WhatsApp DLT paperwork now — needed by Stage 5).

---

## Stage 5 — Marketing engines 3+4, WhatsApp, monthly report (2 weeks)

- **Backend:** `get_cross_sell_targets` (category-level lift, E3),
  `get_push_targets` (E4, dead-stock × category buyers), `get_segments` (RFM),
  segment-aware template tones.
- **WhatsApp channel:** `vinayak/notify/whatsapp.py` via BSP (Gupshup/Interakt),
  template registration flow, DLT compliance; channel choice per contact.
- **Monthly owner report:** `vinayak/workflows/monthly_report.py` — one-page
  HTML/PDF (messages → orders → raw → incremental → best engine → next
  suggestions), auto-drafted to inbox for owner send-off.
- **Frontend:** engine tabs on Campaigns page; report archive.
- **Accept when:** all four engines runnable; a WhatsApp nudge delivers; the
  monthly report generates from real campaign data.

---

## Stage 6 — Agent-Ask upgrade (2–3 weeks) ∥-safe with Stage 5

*Now the agent, arriving last, onto battle-tested parts.*

- Wrap the by-now ~40 proven query functions as read tools (registry from Wave 0;
  descriptions from `TOOL_CATALOG.md`).
- `vinayak/reasoning/agent.py` — raw-SDK tool-calling loop; reuses evidence →
  validate → numeric guard unchanged; memory + multi-turn context carried over.
- `POST /dashboard/ask?engine=agent` flag → shadow comparison vs keyword engine
  on full eval set + new trajectory evals (right tool, right args) + generated
  eval templates → flip default at parity; keyword path remains no-key fallback.
- **Accept when:** agent ≥ keyword engine on evals; compound questions ("top-3
  customers' average order size vs last quarter") answered correctly with cited evidence.

---

## Parallel track — Zoho Phase 2 (∥ any stage, ~1 week when org exists)

Trigger: a Zoho trial/customer org + credentials.
`canonical/zoho_canonical.py` (zb_* → canon_* mapping, `source='zoho_books'`) ·
switch panel queries for Zoho workspaces to canonical reads · invoice line-item
backfill (per-invoice GET, batched) · `/customerpayments` pipeline (exact payment
events) · `zb_contacts` → auto-populate `customer_contacts` (email/phone free).
**Accept when:** a Zoho-only workspace shows a working dashboard + Pulse.

---

## Deliberately after all this (triggers named)
Roles/approver permissions (before any second approver user) · WhatsApp for
collections (after marketing proves the channel) · vector store + Support/Legal
(ticket/doc adapters; Stage-2-of-business decision) · MCP exposure (external
clients wanted) · orchestration framework (multi-agent synapses) · entity
resolution (second source live in same workspace).

## Timeline at a glance

| Stage | Weeks | Cumulative | The demo it unlocks |
|---|---|---|---|
| 1 Pulse | 1.5 | 1.5 | "your dashboard talks" |
| 2 Collections | 2 | 3.5 | "approve 3 chases over tea" |
| 3 Credit gate | 1 | 4.5 | "the brain ripples" (Synapse 1) |
| 4 Engines 1+2 | 2 | 6.5 | "revenue we caused, proven" |
| 5 Engines 3+4 + WA | 2 | 8.5 | "complete marketing solution" |
| 6 Agent Ask | 2–3 | ~11 | "ask it anything" |

Stage 2's end is the **first sellable moment**; Stage 4's end is the **first
referenceable number**. Everything before Stage 6 ships with zero new AI risk.
