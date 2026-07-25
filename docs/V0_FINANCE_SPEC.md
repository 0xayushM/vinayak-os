# V0 Finance Spec — Pulse cards, workflow formulas, tool implementations

> Implementation-ready spec for MVP v0: the Pulse (derived-insight) page, the deep
> collections workflow, the credit gate, and the exact formulas behind each.
> Companion to `TOOL_CATALOG.md`. Everything here runs on data we already sync,
> plus three small new tables defined in §1.

---

## 1. Data prerequisites (build first — everything below depends on them)

### 1.1 `ar_daily_snapshot` — start recording history NOW

**The gap it closes:** `tz_ar_aging` is upserted in place, so we have no memory of
what AR looked like yesterday. Without history there is no aging drift, no inferred
payment dates, no DSO trend, no before/after proof for collections. One insert batch
per successful AR sync (first sync of each day), retained forever (rows are tiny).

```sql
CREATE TABLE ar_daily_snapshot (
  company_id    TEXT NOT NULL,
  snap_date     DATE NOT NULL,
  invoice_ref   TEXT NOT NULL,      -- stable_row_id(invoice_number, customer_name)
  customer_name TEXT,
  outstanding   NUMERIC,
  days_overdue  INT,
  bucket        TEXT,               -- 0-30 / 31-60 / 61-90 / 90+
  PRIMARY KEY (company_id, snap_date, invoice_ref)
);
```

**Inferred payment event** (unlocks true payment behaviour, ~2 weeks after go-live):
an `invoice_ref` present on day D with `outstanding > 0` and absent (or zero) on day
D+1 ⇒ `paid_date ≈ D+1`, `days_to_pay = paid_date − invoice_date`.

### 1.2 `events` — the synapse bus (minimal)

```sql
CREATE TABLE events (
  id BIGSERIAL PRIMARY KEY,
  company_id TEXT NOT NULL,
  event_type TEXT NOT NULL,          -- 'invoice.overdue', 'credit.flagged', ...
  entity_ref TEXT,                   -- e.g. 'customer:DEV COLOUR' / invoice_ref
  payload JSONB,
  created_at TIMESTAMPTZ DEFAULT now(),
  processed_at TIMESTAMPTZ           -- NULL = pending; workers poll
);
CREATE INDEX ON events (company_id, event_type, processed_at);
```

Detection of `invoice.overdue`: during AR snapshot write, any invoice whose
`days_overdue` crossed 0 (or crossed a rung boundary — see §3.3) since the previous
snapshot emits one event. Idempotent by `(invoice_ref, rung)`.

### 1.3 `actions` — the ledger (Layer 9 seed)

```sql
CREATE TABLE actions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id TEXT NOT NULL,
  tool_name  TEXT NOT NULL,          -- 'ar.draft_collection_email'
  entity_ref TEXT,                   -- customer / invoice it acts on
  payload    JSONB,                  -- full draft: to, subject, body, invoice refs
  status     TEXT NOT NULL,          -- proposed | approved | rejected | executed | failed
  gate       TEXT NOT NULL,          -- auto | confirm | human
  proposed_by TEXT,                  -- 'agent' | user email
  decided_by  TEXT, decided_at TIMESTAMPTZ,
  executed_at TIMESTAMPTZ, result JSONB,
  created_at TIMESTAMPTZ DEFAULT now()
);
```

Idempotency rule enforced here: before insert, reject a proposal if an action with
the same `(tool_name, entity_ref, payload->>'rung')` was executed in the last N days
(N per tool; collections N=5).

---

## 2. The Pulse page — 8 cards, exact formulas

Each card = one new query function in `queries.py` (same conventions: company-scoped,
typed dict out, Top-N capped). Each also registers as a read tool for the agent.
Format per card: **headline number · change · one-sentence "why it matters" · deep link**.

### P1 · Aging drift — "is money sliding toward bad?"
- **Formula:** for each bucket b: `drift_b = Σ outstanding in b (today) − Σ (7/30 days ago)`
  from `ar_daily_snapshot`. Headline = net value that moved INTO 61-90 and 90+.
- **Alert when:** inflow to (61-90 ∪ 90+) > 5% of total outstanding.
- **Until history exists:** show bucket totals + "history building — drift in N days".
- Tool: `ar.get_aging_drift(window_days=30)`.

### P2 · Payment behaviour deltas — "who is getting slower?"
- **v1 proxy (day one):** per customer score from the current snapshot:
  `behaviour = w1·(overdue_value/outstanding) + w2·norm(oldest_days_overdue) + w3·norm(wtd_avg_days_overdue)`
  (w = 0.4/0.3/0.3; norm caps at 120d). Rank worst-first, top 8.
- **v2 (with history):** per customer `avg(days_to_pay)` this 90d vs prior 90d from
  inferred payments; headline = customers whose avg worsened > 10 days.
- Tool: `ar.get_payment_behaviour(top_n=8)`.

### P3 · 30-day cash view — "what's coming in vs going out?"
- **Inflow:** `Σ outstanding FROM tz_ar_aging WHERE due_date BETWEEN today AND today+30`
  plus overdue expected: `Σ overdue outstanding × collection_factor` (v1 factor = 0.5,
  calibrated from history later).
- **Outflow:** `Σ po_value FROM tz_purchase_orders WHERE status open AND expected_date ≤ today+30`.
- **Headline:** `net = inflow_due + inflow_expected − outflow`; alert if negative.
- Tool: `fin.get_cash_30d()`.

### P4 · What changed this week — "why is revenue up/down?"
- **Formula:** `this_wk = Σ line_total (last 7 data-days)`; `usual = trailing 8-week
  weekly mean (excluding current)`. `delta% = (this_wk − usual)/usual`.
- **Attribution:** top 3 customers and SKUs by `|contribution|` where
  `contribution_c = Σ this_wk(c) − usual(c)`.
- **Headline:** "Sales ₹X — 12% below your usual week, mostly SHREE SHYAM ordering nothing."
- Tool: `fin.get_week_delta()`.

### P5 · Reorder-cycle status — "which regulars are overdue to order?"
- **Cycle:** per customer with ≥ 4 orders: `median gap between consecutive invoice
  dates` (last 12 mo). Regular ⇢ median ≤ 60d and ≥ 3 gaps.
- **Flag when:** `days_since_last_order > 1.5 × median_gap`.
- **Output:** customer, usual cycle, days silent, avg order value (= the revenue at stake).
- Tool: `crm.get_reorder_status(top_n=10)` — later feeds the marketing engine.

### P6 · Concentration trend — "is dependence growing?"
- **Formula:** top-1 and top-3 revenue share, this 90d vs prior 90d, from
  `tz_sales_invoices`. Headline on change > ±5 pts.
- Tool: `fin.get_concentration_trend()`.

### P7 · Dead-stock delta — "is trapped capital growing?"
- **Formula:** dead-stock value (existing 90-day no-sale rule) computed now vs 30
  days ago. v1: recompute historical value by filtering sales window; no new table needed.
- Tool: `inv.get_dead_stock_delta()`.

### P8 · Anomalies — "things that shouldn't happen"
- Negative stock rows (existing) · invoice > 4× that customer's trailing median
  invoice · new vendor price > 25% above that vendor+SKU's last price ·
  `data.stale` (any report > 25h). Union, capped at 6, each one sentence.
- Tool: `meta.get_anomalies()`.

**UI:** one `/pulse` page (becomes the default landing page), cards sorted by
severity; each card has "Ask about this" (prefills Ask) and, post-Wave-2, an act
button (prefills a chase/PO draft). Also exposed as `GET /dashboard/pulse` returning
all cards — the future WhatsApp morning-brief payload, free.

---

## 3. Collections workflow — the deep spec

### 3.1 Chase priority score
```
priority = outstanding_norm × lateness × behaviour
  outstanding_norm = invoice outstanding / max outstanding in book
  lateness         = 1 + min(days_overdue, 120)/60         # 1..3
  behaviour        = 1 + P2.behaviour_score                 # habitual late-payers rank up
```
Grouped by customer (chase people, not invoices): customer priority = Σ invoice
priorities; list shows per-customer total overdue, oldest invoice, all open invoice
lines. Tool: `ar.get_chase_list()` (supersedes `get_collections_priority`).

### 3.2 Tone ladder (rungs)
| Rung | Trigger (days past due) | Tone | Channel |
|---|---|---|---|
| R1 | 3–14 | friendly reminder, assume oversight | email |
| R2 | 15–29 | firm: amount, invoice list, due dates, request date commitment | email |
| R3 | 30–59 | escalation: payment plan ask, mention credit hold possibility | email, cc owner |
| R4 | 60+ | drafted FOR THE OWNER to send personally (his voice, his relationship) | owner's channel |

Rung boundaries emit `invoice.overdue` events (§1.2) with `payload.rung`; drafts are
generated per **customer** per rung, never per invoice.

### 3.3 Draft generation — `ar.draft_collection_email`
- **Inputs:** `customer_ref`, `rung`. **side_effect:** `writes`. **gate:** `confirm` (always, v0).
- **Gather (internal):** `ar.get_invoice_details` per open invoice, `ar.get_payment_history`
  (P2 data), `memory.get_facts` (terms, relationship notes, promises).
- **Grounding rule:** every ₹ amount and date in the body must come from the gathered
  evidence — same numeric guard as Ask, run on the draft before it reaches the inbox.
- **Output → `actions` row:** `{to, cc, subject, body, invoice_refs[], rung, total_overdue}`.
- **Never:** two active proposals for one customer; a rung lower than the last executed rung.

### 3.4 Promise-to-pay
On approval screen the owner can log "promised ₹X by DATE" →
`memory.save_fact(entity=customer, key=promise_to_pay, value={amount, date})`.
Effects: chases for that customer pause until DATE+2; if snapshot shows it unpaid
after DATE+2 → event `promise.broken` → R-escalation +1 and a Pulse anomaly line.
Kept promises raise the customer's behaviour score.

### 3.5 Outcome measurement (the sales pitch, automated)
- **DSO trend:** weekly DSO from snapshots (existing formula, historized).
- **₹ recovered:** Σ outstanding of invoices that had ≥ 1 executed chase and were
  inferred paid (§1.1) within 14 days of the chase.
- **Aging drift before/after** (P1 series, annotated with go-live date).
- Surface: `/pulse` card + weekly one-page email to the owner (auto-drafted).

### 3.6 Credit gate — `sales.check_customer_credit` (Wave 3)
```
verdict(customer):
  STOP    if overdue_value > 0 AND oldest_days_overdue > terms_days(memory, default 30) + 15
          or promise.broken active
  CAUTION if overdue_value > 0
          or outstanding > 2 × avg_monthly_purchase (12-mo)
  OK      otherwise
returns {verdict, overdue_value, oldest_days, outstanding, terms_source, reasons[]}
```
Read tool (composite, no side effects). Paired action `sales.flag_customer_credit`
(writes `customer_flags` row; quotes/orders pages render the badge; flag clears
automatically when the triggering condition clears). Consumes `invoice.overdue` events.

---

## 4. New/changed query functions (formulas recap)

| Function | Formula essence | Feeds |
|---|---|---|
| `get_aging_drift` | bucket totals today − D-7/D-30 from snapshots | P1, outcome dashboard |
| `get_payment_behaviour` | v1 composite score; v2 Δ avg days-to-pay | P2, chase priority, credit gate |
| `get_cash_30d` | AR by due date + 0.5×overdue − open POs by expected date | P3 |
| `get_week_delta` | weekly Σ vs 8-wk mean + top contributors | P4 |
| `get_reorder_status` | median inter-order gap vs silence, 1.5× flag | P5, marketing engine later |
| `get_concentration_trend` | top-1/3 share 90d vs prior 90d | P6 |
| `get_dead_stock_delta` | dead-stock value now vs 30d-ago window | P7 |
| `get_anomalies` | union of rule flags, capped 6 | P8, watchdog |
| `get_invoice_details` | one invoice: lines, totals, due, days overdue | drafts |
| `get_chase_list` | §3.1 priority, customer-grouped | collections |
| `get_recovery_stats` | §3.5 ₹ recovered + DSO series | proof dashboard |

---

## 5. Updated wave plan (Pulse inserted; v0 = Waves 0–3)

| Wave | Scope | Acceptance criteria |
|---|---|---|
| **0** (3–4d) | Tool contract, registry, executor, trajectory-eval harness; **`ar_daily_snapshot` + `events` + `actions` tables live** (history starts accumulating immediately) | contract reviewed together; snapshot rows appearing daily |
| **1** (1wk) | ~31 ✅ read tools wrapped; agent-powered Ask behind `?engine=agent`; multi-turn carried over | agent ≥ old engine on full eval set incl. trajectory cases |
| **1.5** (1wk) | **Pulse**: 8 query functions + `/pulse` page + cards as read tools | all 8 cards live on kbrushes real data; P1/P2-v2 marked "building history" |
| **2** (1.5wk) | Collections deep: chase list, tone ladder, `draft_collection_email` + numeric guard on drafts, approval inbox UI, ledger execution, promise-to-pay, recovery stats | end-to-end on real data: overdue → draft → approve → sent → logged → recovery tracked; eval: refuses to draft for disputed/promised customers |
| **3** (1wk) | Credit gate: `check_customer_credit`, `flag_customer_credit`, `invoice.overdue` events, badge in quotes/orders UI | Synapse 1 demo: invoice crosses overdue → flag appears with no human touch |
| 4+ | reorder drafts, cashflow forecast v2, marketing engine (reuses P5 + §3 spine) | per TOOL_CATALOG waves |

**v0 definition of done:** a Technoplast owner opens Pulse, sees his aging drifting,
clicks chase, approves three emails, and two weeks later the recovery card shows
money that came home — with every number traceable.
