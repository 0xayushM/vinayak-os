# BIDE — Development Plan

> **The one document that orders all the work.** It takes BIDE (The Business IDE)
> from its current state to the complete product described in
> `docs/vinayak/The_Business_IDE_BIDE.docx`. Phases are ordered by **engineering
> dependency**, not by calendar: data before intelligence, intelligence before
> action, rails before autonomy. Each phase has a goal, the concrete work, and a
> definition of done that gates the next phase.
>
> Formulas and per-workflow tool maps are not restated here — they live in
> `docs/V0_FINANCE_SPEC.md`, `docs/MARKETING_SPEC.md`, `docs/TOOL_CATALOG.md`,
> `docs/ZOHO_INTEGRATION.md`. The product rationale lives in the BIDE reference.

---

## 0. Where we are today (grounded audit of the codebase)

The substrate and the safe reasoning core are built; the **action half** is the
work ahead. Layer status, read directly from `vinayak/` and `apps/web/`:

| Layer | Status | What exists in code today | What is missing |
|---|---|---|---|
| **0 · Foundations** | ✅ BUILT | FastAPI monorepo (`api/main.py`), `config.py` (env-driven), Postgres/Supabase via `asyncpg`/`psycopg2`, Docker + Railway/AppRunner/Vercel deploy | Structured/queryable logging, request tracing, error alerting, CI eval-gate |
| **1 · Identity & tenancy** | ✅ BUILT | bcrypt + JWT in httpOnly cookie (`routes/auth.py`), BFF proxy, `require_workspace` scoping every query by `company_id` (`routes/workspaces.py`) | Roles (owner/admin/member/viewer) + **who may approve money**, invites, password reset, usage analytics |
| **2 · Ingestion** | ✅ BUILT (TranzAct) · 🟡 Zoho (provisional) | 10 TranzAct pipelines + `BasePipeline` contract, `APScheduler`, resumable cursor, Fernet-encrypted creds, content-hash upsert; Zoho pipelines built to the documented Zoho Books v3 API (`pipelines/zoho/`: contacts, items, invoices, bills) | **Zoho unverified against a live org** (no account yet); Zoho invoice/bill **line items** not ingested (list endpoint = headers only) — decide whether to pull details into `zb_invoice_lines`; webhooks; connector health surface |
| **3 · Canonical** | 🟢 MOSTLY DONE | `canon_*` tables + `ingest_issues`; **all business-data panels now read `canon_*_flat`** — sales, AR, inventory, purchases (010), purchase orders (011), sales orders (012), quotes (013), GRN (014), production + routing (015). Only `tz_sync_runs` (sync audit) stays raw. | `zoho_canonical.py` (Zoho → canon); GLEntry object; entity resolution across sources |
| **4 · Read & present** | ✅ BUILT | 55 functions in `schema/queries.py`, 45 dashboard endpoints (`routes/dashboard.py`), Next.js dashboard (`apps/web`, SWR, freshness per panel) | Pulse landing page, Approval Inbox, notifications feed, brain-graph view |
| **5 · Memory** | 🟢 MOSTLY DONE | `memory/store.py` (profile, facts, supersede, **decay**), chat threads + history; **multi-turn is live** (`answer(history_turns=…)` + `rewrite_followup`, `/ask` passes recent turns); **`entity_summary` synthesis** (migration 016 + `memory/entity_summary.py`, refreshed after every canonical rebuild, with a payment-terms contradiction check) | Episodic log from the `actions` ledger; vector store (knowledge plane, Phase 7) |
| **6 · Reasoning base** | ✅ BUILT | `reasoning/engine.py` — deterministic retrieve→reason→validate, numeric guard, three gates; `POST /dashboard/ask` is **live**; optional Claude phrasing (`reasoning/llm.py`); eval harness with **`citation_compliance` metric** + `ship_blocked` gate (`eval/harness.py`, `eval/cases.py`), CI ship-block wired (`.github/workflows/ci.yml`), gate logic unit-tested (`test_eval_metrics.py`) | Expand the golden set toward 50 hand-verified questions; record the raw-dump baseline to beat |
| **7 · Tools** | 🟢 READ TOOLS DONE | `tools/contract.py` + registry + executor; **17 read tools registered** (`tools/read_tools.py`: finance/revenue/AR/inventory/purchases) wrapping the proven query fns, each returning Evidence + quality; catalog at `GET /dashboard/tools` | Action tools (draft_chase, etc.) — Phase 4; MCP server exposure — Phase 7 |
| **8 · Agent core** | 🟢 FIRST CUT | `reasoning/agent.py` — raw-SDK tool-use loop, grounding gate (money figures must trace to tool evidence), confidence derivation, engine fallback; wired into `/ask` behind `AGENT_MODE` (shadow) | Shadow-run vs keyword at scale, then flip; model tiering per-question; the deterministic action authorizer (with Phase 4) |
| **9 · Action spine** | 🟢 FIRST ACTION LIVE | `actions` ledger + executor propose path (idempotency-guarded); **first action tool `collections.draft_chase`** (proposes a grounded payment reminder, never sends); **Approval Inbox** UI + API (`/dashboard/actions`, `/actions/{id}/decide`); "Draft reminder" button on Collections | The actual send after approval (email provider + `customer_contacts`); role-gated approval; WhatsApp; escalation routing; more action tools |
| **10 · Workflows & synapses** | 🟠 SEEDED | `events` table exists | No event emission/consumption, no declarative workflow config, no synapse wired |
| **11 · Scale-out** | 🔴 TO BUILD | Adapter architecture leaves a slot for source #3 | More adapters (Tally/Busy), multi-company, knowledge plane (RAG+KG), infra hardening, MCP |

**One-line summary:** BIDE today is a trustworthy, grounded analytics product —
it ingests, canonicalises (for the core objects), serves a live dashboard, and
answers questions with calibrated confidence and citations. The remaining build
gives it **hands**: the tool layer, the tool-calling agent, the action/approval
spine, and the synapse bus — then the revenue engines and scale-out.

---

## 1. Standing disciplines (every phase, non-negotiable)

- **Deterministic-first.** Numbers come from `queries.py`; the model may phrase
  but never originates a figure. The keyword reasoning path stays as the
  no-API-key fallback permanently.
- **Writes only propose; humans execute; money never automates.** Every non-`read`
  tool writes to the `actions` ledger and waits for a human. `moves_money` /
  `files_regulator` always terminate at a person, regardless of confidence.
- **Every ₹ traces to evidence** — in answers, drafts, content, and suggestions.
  The numeric guard blocks any money figure that wasn't computed.
- **No AI feature ships without an eval.** CI runs the harness and ship-blocks on
  any unsupported-claim regression.
- **Earned complexity.** Build a layer/feature only when a named case needs it and
  it beats the raw-dump baseline. Keep raw rows forever so anything can be re-derived.
- **Provenance & tenancy everywhere.** Every row and tool result carries its source
  and freshness; `company_id` is injected by the layer, never chosen by the model.

---

## 2. The phases (dependency-ordered)

### Phase 1 — Finish the substrate & the trust harness
*Goal: every panel and every future tool reads one clean canonical model, a second
source is proven, and a scoreboard gates every change. This is the moat; finish it
before adding autonomy.*

- **Complete canonicalisation.** Repoint the remaining query functions
  (purchases, orders, quotes, GRN, production, routing) from `tz_*` to `canon_*`
  flat views. Add the canonical objects those need — `canon_purchase_order`,
  `canon_purchase_invoice`, `canon_sales_order`, `canon_production`, `canon_grn`,
  `canon_gl_entry` — **additively**, with schema versioning. Reconcile every
  headline total to the pre-refactor value.
- **Second adapter to canonical (Zoho).** Build `canonical/zoho_canonical.py`
  (`zb_* → canon_*`) so a Zoho-only workspace is served entirely from canonical.
  This is the proof the model is genuinely source-independent. `zb_contacts` →
  auto-populate a `customer_contacts` table (contact data arrives free).
- **Entity resolution.** The same customer from two sources (or spelled two ways)
  resolves to one canonical entity.
- **Ingestion hardening.** Formalise the reliability contract (atomic per run,
  bounded freshness alert), a per-source daily success-rate metric over
  `tz_sync_runs`, and a freshness watchdog (`tech.alert_stale_data`). Add Zoho
  webhooks as the first real-time trigger source.
- **Trust harness.** Freeze a golden question set with hand-verified answers
  (`eval/golden_set.py`); add a **citation-compliance metric** (every stated fact
  traces to evidence; reported as %, target 100) and an **unsupported-claim rate**;
  record the raw-dump baseline to beat; wire the harness into CI as a ship-block.
- **Memory depth.** Feed recent conversation turns back into the reasoner
  (multi-turn — so "which of those are overdue?" resolves "those"); add the
  `entity_summary` synthesis job (per-entity aggregates + facts + contradictions,
  refreshed after each sync).

**Definition of done:** every dashboard panel reads `canon_*`; a Zoho-only
workspace answers correctly from canonical; the golden set runs in CI and blocks
merges on regression; a follow-up question resolves context from memory.

---

### Phase 2 — The tool layer (Layer 7)
*Goal: turn the proven query functions into a catalogue the agent can call. No new
data work — this is a thin, well-tested wrapping over what already returns evidence.*

- **Register read tools** over the ~40 proven query functions using the existing
  `@tool` contract and `domain.verb_noun` names — e.g. `revenue.get_summary`,
  `ar.get_summary`, `ar.get_collections_priority`, `inventory.get_dead_stock`,
  `customers.get_concentration`, `purchases.get_top_vendors`. Each returns
  pre-aggregated data + tagged `Evidence` + `quality` signals; all `side_effect="read"`.
- **Register meta & memory tools**: `meta.get_data_freshness`,
  `meta.get_ingest_quality`, `memory.get_business_profile`, `memory.get_facts`,
  `memory.save_fact` (the only writer here; still proposes via the ledger).
- **Caps & provenance** enforced centrally (top-N, `{plane, source, fetched_at}`
  on every result). Emit Anthropic tool schemas from the registry
  (`anthropic_schemas`), and keep the registry MCP-ready.
- **Tests + tool-level evals**: every tool has a unit test and a golden call.

**Definition of done:** the registry is populated with read/meta/memory tools;
`registry.anthropic_schemas()` returns a valid, tenant-safe tool list; every tool
is covered by a test.

---

### Phase 3 — The agent core (Layer 8)
*Goal: let the model drive — choose which tools to call, in what order — while the
grounding guard and confidence authorizer stay deterministic and ours.*

- **Raw Anthropic SDK tool-use loop** (`reasoning/agent.py`): hand the model the
  read-tool schemas + business profile + relevant memory; it loops gather→see→gather;
  the existing validate/numeric-guard spine runs on the final answer (no framework —
  the control loop stays ours).
- **Deterministic confidence authorizer** (`tools/executor.py` extension): grades
  a proposed action from `side_effect` + `ToolResult.quality`, routing CERTAIN /
  PROBABLE / UNCERTAIN. Read tools run inline; everything else is proposed.
- **Model tiering**: fast model for clean lookups, stronger for judgement; per-call
  cost logged; prompt caching on the system + profile prefix.
- **Shadow-run** the agent against the keyword reasoning path on the golden set;
  **flip to the agent at parity**, keeping the keyword path as the no-key fallback.
- **Trajectory evals**: score tool-selection, not just the final answer.

**Definition of done:** the agent answers via tool-calling at or above the keyword
engine's golden-set scores; the authorizer correctly routes a proposed action;
a fabrication attempt is still blocked.

---

### Phase 4 — The action spine & the first actions (Layer 9)
*Goal: BIDE takes its first real-world action — safely, reversibly, human-gated.
The `actions`/`events` tables already exist; wire the full path around them.*

- **Roles & approver** (finish Layer 1): add owner/admin/member/viewer and the
  "may approve money" permission that gates the inbox.
- **Approval Inbox UI** (`apps/web`): list proposed actions with a preview,
  dry-run, and approve/reject; role-gated; every state (proposed → approved →
  executed → failed) recorded with inputs, gate decision, and result. Idempotent
  (never send the same chase twice).
- **First action tool — AR collections chase.** `collections.draft_chase`
  (`side_effect="writes"`): a daily scan drafts a personalised, evidence-grounded
  reminder from real outstanding figures (numeric guard applies); a tone ladder;
  send via Resend/SMTP after approval. `customer_contacts` capture screen + CSV
  import (built once; the marketing engines reuse it).
- **Notifications**: email / WhatsApp (DLT paperwork started here) / in-app, so
  people are told what needs them and what BIDE did.

**Definition of done:** overdue invoice → drafted chase → owner approves → email
sends → recorded, end-to-end on real data; the "must refuse to act" tests pass;
money never moves without a human.

---

### Phase 5 — Events & the first synapses (Layer 10)
*Goal: one event in one field ripples into workflows in others — the thing that
makes BIDE a brain and not a pile of bots.*

- **Event emission + worker.** Emit `invoice.overdue` from the AR sync into the
  `events` table; a Postgres-backed worker dispatches to subscribers (no new infra
  — a table + worker is enough at this volume).
- **First synapse — Accounts → Sales.** A deterministic credit/concentration
  verdict function; a `customer_flags` table; badges on Quotes / Orders / Customers
  ("this customer already owes you — think before extending more credit"). This is
  the flagship: the data exists and the owner feels it immediately.
- **Declarative workflows.** Represent a workflow as data — trigger + gather tools
  + action tool + gate policy — so new workflows become configuration, not code.
- **More synapses** as the data supports: dead stock → Strategy (trapped capital),
  Support+CRM+Accounts → churn score.

**Definition of done:** one published event drives auto-updates across ≥2 fields;
at least one synapse runs end-to-end with its action human-gated; a new workflow
can be added as data.

---

### Phase 6 — Revenue engines & broader workflows
*Goal: turn the substrate + agent + action spine into measurable revenue actions,
and broaden coverage across the 13 fields wherever current data allows.*

- **Marketing engines 1–4** (`MARKETING_SPEC`): Reorder Radar, Win-Back,
  Cross-Sell, Stock & Season Push. `campaigns` / `campaign_targets` tables; the
  **80/20 hold-back** so caused revenue is proven; batch approval in the inbox; a
  nightly attribution job. Every send writes an origination row.
- **Strategy mode**: KPI-vs-target tracking + rule-derived suggestions
  ("₹X dead stock → clearance experiment") written as draft experiments the owner
  accepts/acts on; the LLM phrases, rules compute.
- **Content & lead workflows**: content generation from business facts/catalog;
  lead capture + follow-up sequencing (the pipeline machine) with attribution.
- **Broaden field workflows the current data supports**: cashflow forecasting,
  auto-reorder draft POs (money-gated), ABC + stockout prediction, customer-360 +
  health score v1, deal forecasting/pipeline hygiene (reads), delay-exception and
  proactive-order notices (events + notify now exist).

**Definition of done:** each engine produces owner-approved actions with a monthly
report showing raw and **incremental** (hold-back-proven) revenue; strategy
suggestions are logged and acted on; attribution rows accumulate from day one.

---

### Phase 7 — Scale-out, new domains & hardening (Layer 11)
*Goal: only after one vertical demonstrably works — widen sources, unlock the
document-driven fields, and make it fast and cheap at load.*

- **More adapters & multi-company**: Tally / Busy as the market or sister
  companies demand (the adapter slot is reserved); onboard multiple companies on
  the same engine; cross-source reconciliation.
- **Knowledge plane (RAG + KG)**: `knowledge_source`/`_chunk` (pgvector) +
  `knowledge_node`/`_edge`, walled off from the structured plane, meeting it only
  at the tool interface. Unlocks Support tier-1 deflection, Legal document Q&A,
  HR policy helpdesk, and R&D need-mining.
- **Infra hardening (provider-agnostic)**: Postgres connection pooler (H1), Redis
  cache for the KPI endpoints (H2), move sync to Celery workers (H3), dockerise +
  autoscale (H4), read replicas (H5), guard the LLM path with per-tenant rate
  limits + caching (H6).
- **Interfaces & orchestration**: expose the tool registry over **MCP** for
  third-party clients; adopt a heavier agent-orchestration framework **only** when
  multi-agent handoffs (the synapses) and cross-run observability justify it — and
  even then, the gate stays ours.

**Definition of done:** a second vertical runs on the same engine with near-zero
query/memory/AI changes; the KPI endpoints are cache-served and a load test of
1000 concurrent users is stable; the knowledge plane answers a cited question
without ever originating a number.

---

## 3. What unlocks what (dependency graph)

```
Phase 1 (canonical complete + trust harness + memory depth)
   │  everything reads one clean model; every change is measurable
   ▼
Phase 2 (read tools)  ──▶  Phase 3 (agent core)
   │                          │  the model can now drive, safely
   ▼                          ▼
Phase 4 (action spine + first action) ──▶ Phase 5 (events + synapses)
   │  BIDE gets hands, human-gated          │  one brain, not many bots
   ▼                                         ▼
Phase 6 (revenue engines + broader workflows)
   │  measurable, owner-approved value across fields
   ▼
Phase 7 (scale-out, knowledge plane, hardening, MCP)
```

**Blocked until a named adapter/plane lands:** Support ×7 (ticket/email intake +
vector), deep Finance ×11 (GL / bank / GST — a ledger source like Busy or Zoho GL
may unlock transaction categorisation and statements earlier; revisit after the
Zoho-canonical spike), People ×9 (HR source), Legal ×6 (documents + vector),
advanced Production ×4 (machine/sensor/camera telemetry). Win/loss analysis is
cheap to unblock — add a loss-reason field to the quotes UI in Phase 6.

---

## 4. Per-layer completion map (remaining work → phase)

| Layer | Remaining work → phase |
|---|---|
| 0 Foundations | structured logging + error alerting → P1 · incident runbook → P7 |
| 1 Identity | roles/approver → P4 · usage analytics → P1 · invites + reset → P7 |
| 2 Ingestion | Zoho canonical + reliability metric + freshness watchdog → P1 · webhooks → P1 · Tally/Busy → P7 |
| 3 Canonical | remaining panels → canonical + new objects → P1 · `zoho_canonical` → P1 · entity resolution → P1 |
| 4 Read & present | Pulse + criterion/health surfaces → P1 · Approval Inbox → P4 · engine/campaign UIs → P6 · brain-graph view → P7 |
| 5 Memory | multi-turn + `entity_summary` → P1 · episodic from `actions` → P4 · vector store → P7 |
| 6 Reasoning | golden set freeze + citation metric + CI gate → P1 · agent path → P3 (keyword stays as fallback) |
| 7 Tools | read/meta/memory tools → P2 · action tools register from P4 onward |
| 8 Agent core | raw-SDK loop + authorizer + model tiering → P3 |
| 9 Action spine | inbox + email executor → P4 · batch approve + notifications → P6 · escalation → P7 |
| 10 Workflows/synapses | events emit + first synapse → P5 · declarative config → P5 · more synapses → P6 |
| 11 Scale-out | adapters + multi-company → P7 · knowledge plane → P7 · infra hardening + MCP → P7 |

---

## 5. First steps (to begin Phase 1 now)

1. ~~Repoint the purchases/orders/quotes/GRN/production/routing query functions to
   `canon_*`~~ — **DONE** (migrations 010–015). Every business-data panel now reads
   canonical; run the migrations + `python -m vinayak.canonical.tranzact_canonical`
   and reconcile each headline total against pre-refactor values.
2. Build `canonical/zoho_canonical.py` — **built to the documented Zoho Books v3
   API, but PROVISIONAL** (no live org yet; line-items decision open — see the
   module header). Rebuilt after `/zoho/sync`; freshness badge source-aware in
   `_last_sync`. Verify against a real org before relying on it. Still:
   `customer_contacts` from `zb_contacts`; entity resolution across sources.
3. ~~Add the citation-compliance metric + CI ship-block~~ — **DONE**
   (`citation_compliance` in `eval/harness.py`, gate unit-tested). Still: grow the
   golden set toward 50 hand-verified questions; record the raw-dump baseline.
4. ~~Add multi-turn context + the `entity_summary` synthesis job~~ — **DONE**
   (multi-turn was already live; `entity_summary` now refreshes after every
   canonical rebuild). Still open in Phase 1: grow the golden set to 50 + record
   the raw-dump baseline (need hand-verified answers); `customer_contacts` from
   `zb_contacts`; entity resolution across sources.

**Phase 1 status: the engineering pillars are complete** — canonical model
(all feeds, both sources), source-aware freshness, the citation-compliance gate
in CI, multi-turn memory, and entity-summary synthesis. What remains needs
domain input (the 50-question golden set + raw-dump baseline) or is small
follow-up (`customer_contacts`, entity resolution). Phase 2 — the read-tool wraps
over the proven query functions — is the cheapest high-leverage next step toward
the agent.
