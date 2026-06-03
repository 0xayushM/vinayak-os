# Business IDE — Progress Tracker & Master Checklist

Maps the **Business IDE Master Document** against what the product actually has
today, then lays out — in execution order — what to build next and what to learn
to build it.

Legend:  `[x]` done · `[~]` partial · `[ ]` not started

---

## Part A — Where we are vs. the plan (the honest scorecard)

The plan says: build the four layers **in order**, and do not polish Layer 3
(the dashboard) before Layer 0 (the parser) is solid. We did the opposite — we
have a strong Layer 1 + Layer 3 for one source, and Layers 0 and 2 are still
shaped around Tranzact, not canonical. That's fine as a *Slice 1 dashboard*, but
the moat (canonical parser + memory) is the unbuilt part.

| Layer | Plan | Today | Status |
|------|------|-------|--------|
| **0 — Ingestion & Parser (the moat)** | Canonical objects (SalesInvoice, Customer, InventoryItem, Payment, PurchaseOrder, GLEntry) + per-source adapters + log everything unmappable | 10 Tranzact pipelines map into **Tranzact-shaped `tz_*` tables**, not canonical objects. Deterministic dedup keys now exist. No canonical schema, no `ingest_issues` log, one source only. | `[~]` ~25% |
| **1 — Storage & Aggregation** | Postgres canonical store + pre-aggregated KPIs so the AI gets small payloads | Postgres (Supabase) + ~30 pre-aggregated query functions, multi-tenant `company_id` scoping, date windows, dual-basis revenue. No materialized views / Redis cache / pgvector / audit log. | `[~]` ~80% |
| **2 — Context & Memory** | Business profile seeded at onboarding + a memory loop that persists owner corrections | None. Onboarding only connects Tranzact; no profile questionnaire; no `memory_fact` store; no correction loop. | `[ ]` 0% |
| **3 — Reasoning & Interface** | KPI cockpit **+ AI chat** with intent parser, domain router, 3 gates, calibrated confidence | Dashboard is strong (KPI cards, charts, detail tables, sync watchdog, notifications). **No AI, no chat, no confidence gates, no LLM integration at all.** | `[~]` ~40% |

**Slice status**

- `[~]` **Slice 1 — Tranzact + Trading:** Layer 1 + dashboard done; canonical parser, memory, AI chat, confidence, and ground-truth validation **not** done. This is the slice to *finish* before anything else.
- `[ ]` **Slice 2 — Tally + Manufacturing:** not started.
- `[ ]` **Slice 3 — Busy + Retail:** not started.

**Infra status**

- `[x]` FastAPI backend · `[x]` PostgreSQL · `[x]` React + Recharts + Tailwind · `[x]` Multi-tenant isolation (`company_id`) · `[x]` Background sync (threads) with hard timeout + notifications
- `[ ]` Redis cache · `[ ]` Celery job queue · `[ ]` pgvector · `[ ]` Claude API + prompt caching · `[ ]` Audit log · `[ ]` Monitoring (latency / confidence distribution / memory hit-rate)

**The one-line read:** the hook (dashboard) is built; the moat (canonical parser
+ memory + calibrated AI) is not. Everything below points at the moat.

---

## Part B — The master checklist, in execution order

Ordered so each step de-risks the next. Don't jump ahead — the document's #3
"what kills you" is *building the abstract version before the concrete one ships*.

### Phase 0 — Decisions to lock before building (1–2 days)

- [ ] Confirm **one vertical** for Slice 1: **Trading/Distribution** (per the doc).
- [ ] Confirm the **first-cut canonical objects**: `SalesInvoice`, `Customer`, `InventoryItem`, `Payment` (add `PurchaseOrder`, `GLEntry` in Slice 2).
- [ ] Confirm **Path A — white-glove onboarding** (not self-serve) as the go-to-market.
- [ ] Pick the **Agarwal company with the cleanest Tranzact data** as the Slice 1 sandbox.
- [ ] Write the **first 10–15 real questions** that owner asks monthly (these become ground-truth + drive the whole reasoning design).

### Phase 1 — Layer 0: canonical schema + Tranzact as an adapter (the moat begins)

- [ ] Define canonical tables: `canon_sales_invoice` (+lines), `canon_customer`, `canon_inventory_item`, `canon_payment` — each with the envelope `(id, company_id, source, source_ref, ingested_at, confidence, raw jsonb)`.
- [ ] Create `ingest_issues (company_id, source, source_ref, field, reason)` — the "log everything you can't map, never guess" table. This is your parser backlog.
- [ ] Define the **`SourceAdapter` contract**: `extract() → map() → load()`.
- [ ] Refactor the 10 Tranzact pipelines into the **first adapter**: map `tz_*` rows → `canon_*` (keep `raw`, log unmapped to `ingest_issues`).
- [ ] Repoint `queries.py` to read `canon_*` instead of `tz_*` (dashboard looks identical, but is now source-independent).
- [ ] Build a **data-quality view**: per source, % rows mapped, top unmapped fields. (Doc: "build a data quality dashboard before the AI chat.")
- [ ] **Done when:** a Tranzact row's full journey (raw → canon → query → panel) is traceable, and adding a new source means writing one adapter and touching zero query functions.

### Phase 2 — Layer 2: business profile + the memory loop (the actual moat)

- [ ] **Onboarding questionnaire** (~10 min) seeding the business profile: industry/sub-vertical, fiscal year, GST, currency, healthy-margin benchmark, seasonality, key customers + special terms, KPIs the owner cares about.
- [ ] `memory_fact` table: `(entity_type, entity_ref, claim_key, claim_value, origin, confidence, created_at, source_msg_id, valid_until, last_validated_at, status, superseded_by)`.
- [ ] **Capture loop v1:** intercept every owner correction in chat → persist as a structured fact (the doc's smallest viable memory loop) → reload on subsequent queries.
- [ ] **Decay/re-validation:** flag facts that go stale (time-based `valid_until`, or contradicted by live data) and re-ask instead of silently repeating. (This is the safeguard against confident-wrong memory.)
- [ ] Render `customers/<name>.md` style facts as a **read-only view** of active facts (DB is source of truth).
- [ ] **Done when:** correcting the AI once changes its answer next time, and a fact that contradicts the data gets re-asked.

### Phase 3 — Layer 3: the AI reasoning pipeline + calibrated confidence

- [ ] Claude API integration (messages format, system prompt, **prompt caching** for system prompt + business profile, streaming).
- [ ] Build the 8-stage pipeline: **Intent parser → Domain router → Context loader → Data gate → Rule gate → Confidence scorer → LLM generator → Memory writer.**
- [ ] **Structured output schema:** every answer returns `{ answer, confidence_level, assumptions, data_used, what_i_dont_know }`.
- [ ] **3 gates that make "say no" structural, not just a prompt:** Data Gate (fresh + complete enough?), Rule Gate (defined rule exists?), Confidence Gate (CERTAIN / PROBABLE / UNCERTAIN).
- [ ] **Tool use / function calling:** let the AI call your `queries.py` functions rather than pre-injecting data.
- [ ] Chat UI in the dashboard with streaming + the three confidence labels rendered distinctly (plain / flagged / a question), plus data-freshness indicator.
- [ ] **Done when:** no AI response ships without a confidence label, and a fabricated/unsupported number is blocked before display.

### Phase 4 — Validation harness (your substitute for Cursor's compiler)

- [ ] **Ground-truth Q&A set:** 50 questions, correct answer hand-computed from raw data.
- [ ] **Confidence calibration set:** 20 answerable + 20 unanswerable questions; AI must score both correctly.
- [ ] **Memory test set:** 10 corrections; verify persisted + reloaded.
- [ ] **Edge-case library:** stale data, missing months, partial imports, duplicates — AI must degrade gracefully.
- [ ] Track release-over-release: **unsupported-claim rate** (ship-blocker if it rises), bucket accuracy, correct-refusal rate.

### Phase 5 — First owner session + finish Slice 1

- [ ] Onboard the chosen Agarwal company end-to-end.
- [ ] Sit with the owner, record every question and every place the AI fails → feed the correction log + eval set.
- [ ] Start tracking **onboarding-days-per-customer** (cap 3 weeks now → target 3 days by customer 10).

### Phase 6 — Slice 2: Tally + Manufacturing (only after Slice 1 is live with a real user)

- [ ] Tally XML-over-HTTP / ODBC adapter (hardest, biggest Indian-SMB footprint).
- [ ] Extend canonical schema: `PurchaseOrder`, `ProductionOrder`, `BOM`, `GLEntry`.
- [ ] Inventory intelligence: dead-stock, reorder point, turnover by SKU.
- [ ] First **outside** paying customer (white-glove) to feel the plumbing pain.
- [ ] **Success test:** how little of the query/memory/AI layer changed? If almost none → the engine generalizes.

### Phase 7 — Slice 3: Busy + Retail / multi-location

- [ ] Busy adapter (multi-location stock, daily sales summary, GST view).
- [ ] Cross-source intelligence (same business on Tally + Busy).
- [ ] Industry benchmark layer (anonymized peers).
- [ ] Assess self-serve readiness after 8–10 white-glove customers.

### Ongoing guardrails (the 5 "what kills you")

- [ ] Onboarding days must **shrink** per customer (not become consulting-in-SaaS-costume).
- [ ] The 3 gates ship **before** any owner uses the AI (confident-wrong = trust dead in one session).
- [ ] No architectural generalization until Slice 1 is live with a real user.
- [ ] Every adapter logs what it can't map; data-quality dashboard before AI chat.
- [ ] Prompt caching + aggressive pre-aggregation from day 1 (LLM cost control).

---

## Part C — What you must learn & master (ordered to match the build)

The doc's philosophy: *be a builder who understands enough to make correct
architectural decisions and debug what breaks* — not a researcher. Learn each
pillar **just before** the phase that needs it.

### Now — needed for Phases 1–2 (Data Engineering, Pillar 2 — the moat)

- [ ] **PostgreSQL deeply:** window functions, CTEs, materialized views, **JSONB** (for the flexible `raw` envelope), indexing. *(You already use most of this — go deeper on JSONB + materialized views.)*
- [ ] **Canonical schema / data-normalization design:** how to model `SalesInvoice` so Tally, Busy, Tranzact all map cleanly; **schema versioning** for backward compatibility.
- [ ] **ETL pipeline design:** Extract → Transform (clean/validate/normalize) → Load; validation & anomaly detection at ingestion (never silently drop/coerce).
- [ ] Tooling: **pandas + openpyxl** (Excel chaos), **SQLAlchemy**; later **dbt** to version aggregation logic as SQL models.

### Next — needed for Phase 3 (Context Engineering, Pillar 1 — most important for the AI)

- [ ] **RAG**: retrieve relevant data and inject it into context.
- [ ] **Token-budget management:** allocate the context window across system prompt / business profile / memory / retrieved data / output.
- [ ] **The four context failure modes** and their business equivalents: Poisoning→stale data; Lost-in-the-Middle→anomaly buried in 40 metrics; Confusion→mixing vertical benchmarks; Clash→contradictory instructions.
- [ ] **Prompt engineering for structured JSON output** with confidence levels.
- [ ] Read: BriefEngine case study §2–3 (your RAG textbook), Anthropic prompt-engineering docs, "Lost in the Middle" (Liu et al., 2023). Rebuild the BriefEngine `ContextEngine` class for business payloads.

### Alongside Phase 3 (LLM Integration, Pillar 3)

- [ ] **Claude API:** messages format, system prompts, **tool use / function calling**, streaming.
- [ ] **Structured output + confidence calibration through prompting** (CERTAIN / PROBABLE / UNCERTAIN).
- [ ] Multi-turn conversation with persistent business context (state across sessions without re-injecting everything).

### As needed — Backend (Pillar 4)  *(you already have most of this)*

- [x] FastAPI, REST design, multi-tenant isolation, background jobs (you have threads + watchdog).
- [ ] **Celery + Redis** for async ingestion that can't block the UI (replace ad-hoc threads at scale).
- [ ] Webhook handling (Tranzact/Tally push), rate limiting, **Claude API cost management + caching**.

### As needed — Frontend (Pillar 5)  *(strongest area already)*

- [x] React, hooks, Recharts/Chart.js KPI cockpit, mobile-responsive, notifications.
- [ ] **Streaming AI responses** (SSE/WebSockets — answer builds like ChatGPT).
- [ ] **UX for trust:** rendering confidence levels, data-freshness, and "what I don't know" without alarming the owner.

---

## The next concrete move

Finish **Slice 1's moat**, not new features: do Phase 1 (canonical schema +
Tranzact adapter + `ingest_issues`), then Phase 2 (business profile + memory loop
v1), then Phase 3 (AI chat behind the 3 gates). Everything you've built so far is
the hook; these three phases are the defensible product.
