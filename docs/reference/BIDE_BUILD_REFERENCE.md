# BIDE Build Reference

> Engineering & product reference, September 2026. How the Business IDE works end to end: architecture, storage and referencing, the agent runtime, orchestrator and harness, tools and MCP, all thirteen fields, the Tally bridge, and the path to becoming the ERP.

How the Business IDE works end to end — what runs where, how every kind of data is stored and referenced, how the agent gathers, decides, acts and learns, how the thirteen business fields become one brain, how Tally on an offline shop-floor PC gets connected, and how a company moves from TranzAct or Tally onto BIDE as its system of record.

**Grounded in** The Business IDE (BIDE) reference (Parts 0–10, 1A) · Business Brain Build Manual · V0 Finance Spec · Tool Catalog · Analytical Handlers Catalog · Marketing Spec · the `os-vinayak` codebase · Tally Solutions integration documentation

Status tags throughout mean: **Built** exists in the repository today · **Partial** the contract exists, the surface or coverage does not · **To build** designed, not started · **Needs data** blocked on a source we do not ingest yet.

## 1 · The aim

BIDE is **one intelligence that runs a business**, not another tool that records it. An ERP logs transactions, a CRM logs contacts, a helpdesk logs tickets, and a person is the connecting intelligence who reads all of them and decides. BIDE takes that seat: it reads every source into one model, reasons across them with confidence it computed, remembers what the owner teaches it, and acts — with a human in the loop wherever money, regulators or relationships are at stake. The chat box, the dashboard and the morning WhatsApp brief are windows onto that one intelligence, not the intelligence itself.

### The three promises

Every capability serves exactly one of three promises, each with its own kind of confidence. **Know**: what is happening now — computed facts, no guesswork. **Understand**: why — inference from patterns, assumptions flagged. **Decide**: what to do — a recommendation with explicit confidence, and where it is safe, the action already prepared.

### The one loop

There is exactly one control loop in the system. A question typed in chat, an event fired when an invoice crosses 30 days overdue, and a 6 a.m. scheduled scan are three triggers into the same six beats. Because there is one loop there is one place to enforce grounding, one place to enforce the gate, and one place to write memory; a new capability is a new trigger, tool or workflow definition, never a new way for the system to behave.

**Trigger** A person asks, an event fires, or a schedule runs

**Gather** Read only through tools; every figure becomes tagged Evidence

**Reason** Form claims — computed, inference or unknown

**Gate** Deterministic code decides how sure we are and what may happen

**Act** Answer, or propose an action to the ledger; execute after approval

**Remember** Write the whole pass back: facts, outcome, episode

### The gate that makes autonomy safe

Every pass ends at a three-way gate. **CERTAIN**: run automatically. **PROBABLE**: the work is done, a person presses yes. **UNCERTAIN**: stop and hand it to a person. The gate is computed by rules we own from real signals — is the data fresh, did the entity resolve unambiguously, what is the side-effect class, what has the owner approved before — never by the model grading itself. One rule never bends: anything that moves money or files with a regulator terminates at a human regardless of confidence. And the model cannot originate a number: it may only repeat figures a tool returned, and a deterministic guard blocks any rupee figure that did not.

The governing test

For every capability: does it beat "dump the data into a chatbot and ask" on a specific, named case? A one-time analysis is a wrapper. A living, always-fresh, owner-corrected, auditable system that also acts is a product. The moat is time and trust — the parser that makes messy ERP data clean, and the memory that compounds — not any single answer or screen.

## 2 · The machine, end to end

Two deployable services and one database, with a small set of frozen contracts between them. Everything that churns — frameworks, models, transports, sources — sits behind a port so it can be swapped without touching the core.

**Browser** Next.js 16 app on Vercel. Dashboard, Inbox, Ask, Settings. Never talks to the backend directly.

**BFF** Next.js route handlers on the same origin. Attach the Supabase access token, the workspace id and the shared internal key; forward server-to-server. The backend URL is a server-only secret.

**API** FastAPI on Railway. Verifies the token, maps email → allowlisted workspaces, injects `company_id` into every read. Serves panels, Ask, the ledger, connections.

**Worker** APScheduler inside the API today; a Celery worker when load demands. Runs syncs, detectors, watchers, the daily brief. The API only enqueues.

**Adapters** TranzAct (reporting API), Zoho Books (REST), Tally (XML gateway via a local bridge), Busy, CSV/email later. Extract → map → load into the canonical model.

**Postgres** Supabase. Raw tables, canonical tables and views, memory, events, actions, episodic log, and — for the knowledge plane only — pgvector.

**Model** Anthropic Claude behind a ModelPort (fast tier for routing and wording, strong tier for judgement). Reached only through tools.

**Channels** Email (Resend/SMTP), WhatsApp Business API, in-app notifications. Executors only; never callable by the model.

### Why this shape

Python for the brain because the data, the SQL and the model SDKs live there; TypeScript for the face because the UI does. A BFF so the browser holds no secrets and the backend can be moved or scaled without the frontend knowing. One Postgres for everything because at this volume a second datastore is a second failure mode: the events bus is a table plus a worker, the vector store is an extension, the cache is a materialised view until Redis is earned. Anthropic's native tool-use behind a port because the tool-calling loop is a few dozen lines we own — and the safety guarantees live in that loop, which is the one thing we never hand to a framework.

### The eight frozen contracts

| Contract             | What it fixes                                                                                                                                                                                                       | Where it lives                        |
|----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------|
| Canonical model      | The one language every layer speaks — Customer, Invoice, SKU, Payment, Order, PO, GRN, Production, Routing, and the objects the other fields add. Sources map into it; it never bends to a source.                  | `canonical/`, migrations 002, 010–017 |
| Evidence             | Every figure the brain may use: stable id, label, raw value, display form, provenance. Grounding, citation and the numeric guard stand on it.                                                                       | `domain/models.py`, `domain/money.py` |
| Tool                 | The only door between the AI and data: typed name and inputs, capped pre-aggregated output, side-effect class, quality signals. `company_id` is injected, never chosen by the model. No tool both reads and writes. | `tools/contract.py`                   |
| Safety spine         | grounded(), confidence(), safe_summary() — one deterministic module outside any orchestrator.                                                                                                                       | `reasoning/safety.py`                 |
| AgentRunner port     | `run(trigger, context) → Answer`. The orchestration engine lives behind it and is swappable.                                                                                                                        | `agents/runner.py`                    |
| Memory schema        | Profile, durable facts that supersede and decay, entity summaries, threads, episodic log — distinct stores, distinct rules.                                                                                         | `memory/`, migrations 003, 006, 016   |
| Event                | A typed event with entity reference, payload, tenancy, idempotency key and processed marker on a shared bus.                                                                                                        | `events` table, migration 008         |
| Tenancy & provenance | Every row and every tool result carries its company, source and freshness.                                                                                                                                          | `api/deps.py`, every query            |

## 3 · How everything is stored and referenced

Every kind of thing the business produces — a transaction, a lead, a document, a fact the owner said, a thing the brain did — lands in exactly one of seven stores, each with its own rule for how it is written, read, and aged. Conflating them is the classic bug; keeping them apart is what makes the system auditable.

### 3.1 Raw — the exact copy

Every row a source returns is stored verbatim in a per-source, per-report table (`tz_*` for TranzAct, `zb_*` for Zoho, `ty_*` for Tally), keyed on `(company_id, raw_id)` where `raw_id` is a content hash of the row's identifying fields. Re-fetching a row overwrites it in place, so re-syncs never inflate counts, and a sync that dies half-way never empties a table — stale is better than empty, enforced at the database. Raw is kept forever so the canonical layer can be rebuilt without touching the source. **Built**

### 3.2 Canonical — the one model

Raw rows are reshaped into business objects independent of where they came from. Every canonical row carries the same envelope:

    id uuid            -- surrogate key
    company_id text    -- tenant; always filtered, injected by the layer
    source text        -- 'tranzact' | 'zoho' | 'tally' | 'busy' | 'bide'
    source_ref text    -- stable key in the source; UNIQUE (company_id, source, source_ref)
    ingested_at, confidence real, raw jsonb

Objects today: `canon_customer`, `canon_sales_invoice` + lines, `canon_payment` (AR), `canon_inventory_item`, `canon_purchase_invoice` + lines, `canon_purchase_order`, `canon_sales_order`, `canon_sales_quotation`, `canon_grn`, `canon_production`, `canon_routing`. Each has a `_flat` view whose columns are exactly what the query layer expects, so a new source becomes a new mapper and zero query changes. Anything a mapper cannot place confidently goes to `ingest_issues` with a reason — never a plausible fake value, never a silent drop. **Built**

Objects the other fields add, all in the same envelope: `canon_vendor`, `canon_gl_entry`, `canon_bank_txn`, `canon_lead`, `canon_deal`, `canon_ticket`, `canon_interaction`, `canon_contract`, `canon_employee`, `canon_work_order` (production done properly), `canon_asset`. Each is added additively with a schema version; nothing existing changes. **To build**

### 3.3 The entity reference — how everything points at everything

One string form is used everywhere a thing is referred to — in memory facts, entity summaries, events, actions, flags, episodes, and tool arguments: `<type>:<canonical code>`. `customer:DEV-COLOUR`, `invoice:SI/26-27/0151`, `sku:PA-14`, `vendor:V0031`, `lead:L-2026-0412`, `ticket:T-8801`, `contract:C-17`. The code is the canonical one, so a customer that arrives from TranzAct as "Dev Colour Pvt Ltd" and from Tally as "DEV COLOUR PVT. LTD." resolves to the same reference once entity resolution has merged them (`canon_entity_alias`: alias → canonical code, with the confidence and who confirmed it). Every table that carries an `entity_ref` can therefore be joined to every other, and the brain can hold a customer's invoices, payments, promises, tickets, contracts and the last three things it did about them in one place.

### 3.4 Memory — what we know that is not in the data

| Store                                                                     | Holds                                                                                                                                                           | Rule                                                                                                                                                                  | Status                      |
|---------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------|
| `business_profile`                                                        | Industry, sub-vertical, fiscal year, GST status, healthy margin, seasonality, KPIs the owner cares about                                                        | One row per company; seeded at onboarding; slow-changing                                                                                                              | **Built**               |
| `memory_fact`                                                             | Owner-taught truths: payment terms, credit limits, cost per SKU, promise-to-pay, relationship notes                                                             | Keyed on (entity_ref, claim_key); a new value supersedes the old; goes stale on expiry or on contradiction with live data, and a stale fact is re-asked, not repeated | **Built**               |
| `entity_summary`                                                          | Reason-once-at-ingest understanding of a customer, vendor or SKU: aggregates + active facts + open contradictions, as JSON and as rendered markdown             | Refreshed after every canonical rebuild; a question about an entity loads one summary, not rows                                                                       | **Built** for customers |
| `chat_thread`, `chat_turn`                                                | Each Ask turn with the full structured answer                                                                                                                   | Scoped to (user, company); recent turns feed the next question                                                                                                        | **Built**               |
| `brain_runs` (episodic)                                                   | Every loop: trigger, tools called, evidence ids, claims, gate decision, action id, outcome, cost, latency                                                       | Append-only from day one; the audit trail and the learning substrate                                                                                                  | **To build**            |
| `knowledge_source`, `knowledge_chunk`, `knowledge_node`, `knowledge_edge` | Owner documents, SOPs, contracts, playbooks, policies — chunked and embedded (pgvector) and linked in a light graph whose nodes may point at a canonical entity | Answers how / why / what does this mean. Never the source of a number. Walled off from the structured plane; they meet only at the tool interface                     | **To build**            |

### 3.5 Events, actions, flags — what the brain does

`events` is the synapse bus: `(company_id, event_type, entity_ref, payload, idempotency_key, created_at, processed_at)`. Detectors write; the worker consumes. `actions` is the ledger: every proposal with its payload, gate, who proposed and decided it, execution result and outcome; idempotent per (tool, entity, rung) inside a window. `customer_flags`, `stock_flags` and the like are the current state a synapse leaves behind so a screen in another field can show a badge without re-deriving anything. `campaigns` and `campaign_targets` hold marketing sends and their hold-back groups. **Partial** — the tables exist; emission, consumption and flags do not.

### 3.6 History — the tables that remember yesterday

Sources are snapshots; they do not remember what receivables looked like last Tuesday. So the system records its own history where the source will not: `ar_daily_snapshot` (already accumulating), and next `ap_daily_snapshot`, `stock_daily_snapshot`, `pipeline_daily_snapshot`. These are what make "drift", "getting slower", inferred payment dates and before/after proof possible. They cost almost nothing and cannot be back-filled, which is why they are written from the first sync.

### 3.7 Group — the Vinayak layer

A workspace is one company. A `groups` row plus `group_members(company_id)` makes nine companies one portfolio for the family that owns them. Group reads are unions over member `company_id`s and are the basis of the group page (§11). Entity resolution runs across the group as well as within a company, so the same customer buying from three sister companies is one `customer:` reference with three sources, and intercompany parties are tagged so they can be netted out.

## 4 · How the agent runs

There is no separate "agent" for each field. There is one runtime with three entrances, a catalogue of tools, and a set of watchers that say which tools to gather with, what to detect, what to compose, and how strictly to gate it.

### 4.1 The three entrances

- **A question.** `POST /dashboard/ask`. The runtime assembles context (profile, relevant facts, entity summaries, recent turns), hands the model the read-tool schemas, and lets it gather over several passes. The final text passes the safety spine; the answer carries a confidence label and the tools it used. **Built**
- **An event.** A detector emits `invoice.overdue{rung:2}`. The worker finds the watchers subscribed to that type, and runs each through the same runtime with a trigger context instead of a question. **To build**
- **A schedule.** After every canonical rebuild, all detectors run for that workspace. Daily at 06:00 IST the Pulse is assembled and phrased into the brief. Monday 08:00 the weekly one-pager is drafted. Monthly, the slow scans (cross-sell patterns, dead-stock delta, concentration trend). **To build**

### 4.2 A pass, step by step

1.
    **Context assembly**The runtime builds the system prompt from a cached stable prefix (instructions + business profile + tool schemas) plus the relevant memory: facts for the entity in question, its entity summary, the last few turns. For an event trigger it also includes the event payload and the watcher's instruction.

2.
    **Gather** The model asks for tools; the executor runs each one in-process, injects `company_id`, caps the output (top-N, bounded payload), and returns the data plus tagged Evidence and quality signals (data_fresh, entity_resolved, source). The model never sees a raw row or the database.

3.
    **Reason** The model writes an answer, or — for a watcher — calls a compose tool (draft a chase, size a PO, word a nudge). Compose tools are pure: they take evidence and return a payload; they cannot send.

4.
    **Guard** The numeric guard scans the text or payload: every rupee figure must match a piece of evidence exactly (rounded display or raw value). One self-correcting retry, then an evidence-only fallback. Nothing invented reaches a screen or a customer.

5.
    **Gate** Deterministic: `side_effect × quality × history × policy`. Read → run. Writes with fresh data, resolved entity, and a good approval history → auto with a cancellable hold. Writes otherwise → confirm in the Inbox. Money or regulator → human, always. Unresolved entity or stale data → escalate with what is missing.

6.
    **Act** Read results return to the model; non-read results are written to the `actions` ledger as proposed, with the evidence that justified them. After a human decision the executor runs the channel (email, WhatsApp, write-back, flag) and records the result.

7.
    **Remember** A `brain_runs` row records the whole pass. Any owner correction becomes a `memory_fact`. Outcomes (paid within 14 days of a chase; nudge followed by an order) are attributed back to the action and the watcher.

### 4.3 Watchers — workflows as data

A watcher is a row in `workflows`, per workspace, switchable by the owner:

    { key: "collections.overdue_rung",
      trigger:  {type: "event", event_type: "invoice.overdue"},
      detector: "ar.detect_rung_crossings",       -- deterministic SQL, emits the events
      gather:   ["ar.get_invoice_details", "ar.get_payment_history", "memory.get_facts"],
      compose:  "collections.draft_chase",         -- side_effect: writes
      gate:     {policy: "confirm", auto_after: 10, caps: {per_entity_days: 7}},
      cooldown: "5d", enabled: true }

New workflows are new rows. The detector is SQL over canonical tables and never calls the model, so the expensive, non-deterministic part (wording) happens only when something has actually been detected. Every watcher ships with eval cases (§5.3) before it can be enabled for a workspace.

### 4.4 Earning autonomy

The gate reads history. Per workspace and per watcher, the ledger knows how many proposals were approved unedited, approved with edits, or rejected. A watcher whose last *N* proposals were approved unedited becomes eligible for auto-execution after a 24-hour hold the owner can cancel from the Inbox; any rejection demotes it. Hard caps sit above this — one outbound message per customer per seven days, nothing to a disputed or promised account, nothing outside working hours — and money and regulator actions never graduate. That is how "the owner approves every message" in month one becomes "the owner reads a summary of what went out" in month six without ever having taken the human out of the money path.

## 5 · Orchestrator, model, harness — and why

### 5.1 The orchestrator

The default `AgentRunner` is an owned, thin loop over Anthropic's native tool-use (`reasoning/agent.py`, wrapped by `agents/native.py`). It is about two hundred lines and does four things: build context, call the model with tool schemas, execute the tools it asks for, and hand the result to the safety spine. It is kept deliberately small because the control loop is exactly where the safety lives — the numeric guard, the gate, the tenancy injection — and coupling that to an external framework's control flow would be the opposite of future-proof. **Built**

**Google ADK** is present as a second implementation of the same port (`agents/adk.py`) and is currently a scaffold: its tool bridge and safety finalisation are real, its session loop is a `TODO`, and selecting it falls back to native. Its role, when it is completed, is orchestration only: it chooses which read tools to call and manages a multi-turn session. It does not learn, remember the business, or grade itself — those are memory, the episodic log and the harness, all of which are ours and identical under either runner. The point at which ADK (or LangGraph) earns adoption is when several agents must hand off to each other — the synapses of §8 running as cooperating sub-agents — and cross-run tracing becomes worth a framework. Until then, the native loop is cheaper, fully understood, and passes the same scoreboard.

### 5.2 The model

Claude via a `ModelPort` with two tiers: a fast model for routing, follow-up rewriting, titles and clean lookups; a strong model for judgement, tool-driven gathering, and final phrasing. The stable prompt prefix is cached so repeat turns are cheap; tool outputs are capped before they reach the model; per-call cost and latency are logged into `brain_runs`. The provider is swappable behind the port; the guarantees do not depend on which model is used because the numbers never come from it.

### 5.3 The harness — the compiler for a system that has no compiler

An LLM feature cannot be type-checked, so the eval suite is what ship-blocks a release. It holds real owner questions with hand-verified answers and grades: *citation compliance* (every computed claim traces to evidence — must be 100%), *correct-refusal rate*, *bucket accuracy* (CERTAIN / PROBABLE / UNCERTAIN landed where expected), and *must-not-say violations*. It grades the deterministic engine on every push in CI, and can grade any runner (`--runner native|adk`) so a swap is proven before it ships. **Built**, 29 cases.

What the harness grows into as the brain gets hands: **trajectory cases** (did the agent call the right tools, in a sensible order, without wandering), **action cases** ("must refuse to draft a chase for a customer with an active promise-to-pay"; "must never propose a PO above the money threshold as auto"), **a raw-dump baseline** (the same questions answered by dumping the data into a chatbot, so the gain is measured, not claimed), and per-watcher golden sets that must pass before that watcher can be enabled for a workspace. Cost-per-question is tracked alongside so the product never gets better by getting expensive.

The harness is also how learning is measured. Memory and the episodic log make the system's answers change over time; the harness is what tells you they changed for the better. "Learning" in BIDE is therefore three concrete mechanisms, not a property of the orchestrator: facts and summaries that accumulate, outcomes attributed to actions, and a scoreboard that is re-run.

## 6 · Tools and MCP

### 6.1 The tool catalogue

A tool is a function the model is allowed to call, declared once against the contract: `domain.verb_noun`, typed inputs, a description the model selects on, a side-effect class, and a function returning `ToolResult(data, evidence, quality)`. Five kinds: *read* (never gated; 38 today), *action* (proposes; 1 today), *memory* (facts, profile, summaries), *meta* (freshness, ingest quality, anomalies), *external* (search, enrichment — executor-side, never callable by the model for sends). Every read tool wraps a proven query function from the same repository the dashboard uses, so a number on a screen and a number in an answer come from the same code.

### 6.2 How a tool call flows

Model returns `tool_use(name, input)` → registry resolves the tool → executor validates inputs against the declared types, injects `company_id` and the user → read: run inline, return data + evidence; non-read: check the idempotency window, call the compose function, write the proposal to the ledger with the gate decision, return `{queued, action_id, gate}` so the model can tell the owner what is waiting → evidence accumulates for the guard. A tool bug is caught and returned as an error result; it can never kill the loop or leak a stack trace to the model.

### 6.3 MCP — the business as a tool for other clients

The Model Context Protocol is a transport, not a rewrite. The registry already emits Anthropic tool schemas; a thin MCP server publishes the same catalogue — read tools first, then compose tools whose results still land in the ledger — so approved external clients can call the business as a tool. Company identity is bound at the server from the client's credential, never passed as an argument; per-client scopes restrict which tool families are visible. **To build**, Stage 2+.

Clients this serves: the owner's WhatsApp assistant (a small bot process that speaks MCP to BIDE and WhatsApp to the owner), Claude Desktop or Cowork for the group CFO, a group-level Naksha-style task app that wants "outstanding for customer X" without re-implementing it, and eventually the marketplace or accounting tools that want to write a lead or read a credit verdict. In the other direction BIDE is an MCP *client* to external servers where that is the cleanest integration — Zoho, Google Workspace, a WhatsApp provider — with those calls wrapped as our external tools so they inherit the same caps and provenance.

## 7 · The thirteen fields

Each field below is described the same way: what it owns, the data it needs and where that data comes from and is stored, how its things are referenced, the tools it reads and acts with, the watchers that run in the background, what it feeds and is fed by, and honestly where it stands. The stack under every field is identical — adapter → canonical → tools → runtime → gate → ledger → memory; only the data, the tools and the watchers differ. Finance is described in the most detail because it is built and because its patterns are the template the others copy.

Field 1

### Finance & Accounts

**Owns** the books, the cash, and compliance. The first vertical, because the data is richest and the truth-test is sharpest.

Data in  
Sales invoices + lines, AR aging, purchase invoices + lines, POs, payments (TranzAct \#29, \#102, \#77, \#3); Zoho invoices/bills/contacts/items; Tally vouchers, ledgers, bills outstanding (§9). Later: bank statements (CSV / account-aggregator), GST portal returns (2A/2B).

Stored as  
`canon_sales_invoice(_line)`, `canon_payment` (AR), `canon_purchase_invoice(_line)`, `canon_purchase_order`; to add: `canon_vendor`, `canon_ap` (bills outstanding), `canon_gl_entry`, `canon_bank_txn`. History: `ar_daily_snapshot` **Built**, `ap_daily_snapshot`.

Referenced by  
`customer:CODE`, `vendor:CODE`, `invoice:NUMBER`, `bill:NUMBER`, `po:NUMBER`. Money facts in memory: `payment_terms_days`, `credit_limit`, `promise_to_pay{amount,date}`, `dispute{invoice,reason}`.

Read tools  
finance.get_overview, revenue.get_summary / trend / daily / by_category, ar.get_summary / exposure, finance.get_collections_priority, finance.get_dso, finance.get_credit_risk, finance.get_cash_movement, purchases.get_summary / top_vendors / open_pos / overdue_pos, meta.get_data_freshness. **Built**. Next: ar.get_aging_drift, ar.get_payment_behaviour, fin.get_cash_30d, fin.get_week_delta, ar.get_invoice_details, ar.get_payment_history, fin.get_working_capital, ap.get_aging, fin.get_recovery_stats.

Action tools  
collections.draft_chase **Built** (rungs R1–R4 to add) · ar.log_promise (writes a fact) · ap.propose_payment_run (moves_money → human) · fin.draft_journal_entry (writes; posts to the ledger source after approval) · gst.assemble_return (files_regulator → human) · fin.flag_anomaly.

Watchers  
Overdue rung crossing → chase draft · Promise broken → escalate · Aging drift \> 5% of book → Pulse alert · Cash 30-day net negative → alert · Duplicate or out-of-pattern payment → hold for review · Vendor price +25% vs last → note · Data stale → badge.

Gate  
Chase drafts: confirm, graduating to auto-with-hold for R1 on trusted customers. Anything that releases money (payment runs, journal posting to the statutory ledger, payroll): human, always. GST filing: human, always.

Feeds / fed by  
Feeds Sales (credit gate), CRM (health), Strategy (working capital, concentration). Fed by Orders (dispatch → invoice), Inventory (valuation), every field that spends.

Status  
**Built** reads, chat, one action end-to-end. **Partial** collections depth, Pulse. **Needs data** for margin (cost per SKU), exact DSO (receipt dates), AP aging (vendor bills mapped), cash position (bank), GST/GL (a ledger source).

**How money is managed, concretely.** An invoice arrives raw, becomes a canonical header and lines with tax separated from goods value, and appears in AR as a `canon_payment` row with days overdue and bucket. Each night the AR book is snapshotted; a row present on day D and gone on D+1 is an inferred payment, which gives days-to-pay per invoice and per customer. Rung detectors compare each open invoice's age to the ladder (3/15/30/60) and emit one idempotent event per (invoice, rung). The collections watcher gathers invoice details, payment history and facts (terms, promises, disputes), composes a per-customer draft under the numeric guard, and proposes it. The owner approves; the executor sends and records; the snapshot later attributes recovered rupees to the chase. Nothing in that chain lets the model touch a number, and every step is in the ledger.

Field 2

### Sales

**Owns** turning interest into revenue: leads, quotes, deals, orders.

Data in  
Quotes and sales orders (TranzAct \#8, \#2) **Built**; leads and deals from the lead-capture hub (§10 of the reference: IndiaMART BuyLeads, website form, WhatsApp, referrals) and any CRM the company already uses; win/loss reasons entered in BIDE.

Stored as  
`canon_sales_quotation`, `canon_sales_order` **Built**; `canon_lead(source, channel, product_interest, stage, lost_reason, owner)`, `canon_deal`, `lead_touch` (every acknowledgement, call, follow-up) **To build**. Lead stage is a state machine: CAPTURED → QUALIFIED → QUOTED → FOLLOW-UP → NEGOTIATING → WON / LOST → NURTURE, and a lead cannot be closed lost until three touches are logged.

Referenced by  
`lead:ID`, `deal:ID`, `quote:NUMBER`, `order:NUMBER`; a won deal links to `customer:CODE`. Facts: `icp_fit`, `relationship_owner`, `do_not_discount`.

Read tools  
quotes.get_summary, orders.get_book_summary / overdue **Built**; sales.get_pipeline, sales.get_stale_leads, sales.get_lead_360, sales.check_customer_credit (composite: AR + facts → OK / CAUTION / STOP), sales.get_conversion_by_source, sales.get_lost_reasons.

Action tools  
sales.draft_quote (from price master, stock and credit; writes) · sales.draft_followup (writes) · sales.flag_customer_credit (writes `customer_flags`) · sales.acknowledge_lead (auto: template within seconds) · sales.update_stage (writes, auto when unambiguous).

Watchers  
New lead → instant acknowledgement + parse product/qty/location → qualification questions · No activity at day 2/5/10 → follow-up draft · Credit verdict flips → badge on quotes/orders and a hold proposal · Quote open \> N days → nudge · Deal closed → win/loss reason required, routed to R&D and Marketing · Pipeline change → forecast recompute → Finance.

Gate  
Acknowledgements and stage hygiene: auto. Follow-ups: confirm, graduating. Quotes above a size, any discount, anything to a flagged customer: human.

Feeds / fed by  
Feeds Orders, Production and Inventory (demand), Finance (forecast), Marketing (what converts). Fed by Finance (credit), Inventory (available to promise), Production (lead times), Marketing (leads), R&D (battlecards).

Status  
**Partial** — quotes/orders reads exist; the credit verdict exists as a query; leads, the state machine and the lead-capture hub are the first build. This is also the vertical where BIDE first becomes a system of record rather than a mirror (§10).

Field 3

### Marketing

**Owns** creating demand. For a manufacturer this is not ads; it is extracting more revenue from customers it already has, and the four engines read the invoice history to do it: *Reorder Radar* (defends order frequency), *Win-Back* (defends customer count), *Cross-Sell* (grows order value), *Stock & Season Push* (frees trapped capital). Revenue = customers × order frequency × order value; each engine defends or grows one lever.

Data in  
Everything it needs is already synced: invoice lines per customer per SKU over time, dead-stock list, seasonality from the profile. The one hard prerequisite is **contacts** — email and WhatsApp per customer (`customer_contacts`, manual, CSV import, auto-filled from Zoho). Later: campaign response, website and marketplace analytics.

Stored as  
`campaigns(engine, audience_rule, incentive_set_by_owner, hold_back_pct)`, `campaign_targets(customer_ref, messaged|held_back, sent_at, ordered_within_90d, revenue)` **To build**.

Referenced by  
`campaign:ID`, targets by `customer:CODE`; content assets in the knowledge plane by `doc:ID`.

Read tools  
crm.get_reorder_status (median inter-order gap, 1.5× rule), crm.get_lapsed (silent \> max(2× gap, 60d), ranked by 12-month revenue × recency), mkt.get_cross_sell_pairs (lift(A→B) ≥ 2 with ≥ 3 supporting customers), inventory.get_dead_stock **Built**, mkt.get_campaign_results (raw vs incremental revenue).

Action tools  
mkt.draft_campaign (writes: audience + per-customer personalised messages; the owner types any incentive — the system never invents a discount) · mkt.draft_content (writes; brand voice from the knowledge plane) · ads.recommend (recommend only; budget changes are money → human).

Watchers  
Daily reorder scan · Weekly win-back scan · Monthly cross-sell and stock-push scans, plus pre-season windows from the profile · Nightly attribution job (messaged vs held-back).

Gate  
Every message confirm, batch-approvable, until a campaign type earns auto for routine nudges. A random 20% of every audience is held back so the incremental revenue is proven, not claimed; both numbers are always shown.

Feeds / fed by  
Feeds Sales (qualified leads, reactivations) and R&D (demand signal). Fed by Support (common questions → content), Sales (what converts), R&D (positioning).

Status  
**To build**; all four engines run on synced data plus contacts. Content and ads workflows need the knowledge plane and external tools.

Field 4

### Support

**Owns** keeping the customers already won.

Data in  
Tickets and messages: a shared support mailbox (IMAP adapter), WhatsApp Business inbound, a web form, later a helpdesk API. Complaint records that today live in WhatsApp groups and notebooks come in through the same capture hub as leads.

Stored as  
`canon_ticket(customer_ref, order_ref, sku_ref, channel, topic, priority, sentiment, status, sla_due)`, `canon_interaction` (every message, both directions); resolved tickets are chunked into the knowledge plane as Q&A.

Referenced by  
`ticket:ID` → `customer:`, `order:`, `sku:`. Facts: `sla_days`, `escalation_contact`.

Read tools  
support.get_open_tickets, support.get_ticket_360 (the ticket plus the customer's orders, outstanding, last interactions), support.get_themes (clustered topics per period), support.get_sla_breaches, docs.search (knowledge plane).

Action tools  
support.draft_reply (writes; from docs + 360) · support.route (auto when classification is clear) · support.escalate (writes; sentiment or SLA) · kb.draft_article (writes; from a resolved ticket).

Watchers  
New ticket → classify + route; simple and confident → draft auto-reply for confirm · Negative sentiment or high-value customer → escalate now · SLA at 80% → alert · Weekly theme clustering → R&D and QA.

Gate  
Routing and SLA alerts auto. Replies confirm, graduating for tier-1 answers from the KB. Anything involving money (credit notes, replacements) human.

Feeds / fed by  
Feeds R&D and QA (field failures), Sales (churn risk), CRM (health). Fed by Orders (status), CRM, Finance.

Status  
**Needs data** — blocked on ticket/email intake and the vector store. Unlocks thirteen workflows and two synapses when it lands, which is why the mailbox adapter is the highest-leverage new source after Tally.

Field 5

### CRM

**Owns** the customer axis of the brain — the one record every other field attaches to.

Data in  
Nothing of its own. CRM is the resolved `customer:` entity plus everything referenced to it: invoices, payments, orders, quotes, tickets, campaigns, interactions, facts. Contact data from `customer_contacts`, Zoho contacts, Tally ledger addresses, the lead hub.

Stored as  
`canon_customer` **Built**, `canon_entity_alias` (resolution), `customer_contacts` **Built**, `canon_interaction`, `entity_summary` **Built** (the 360 page comes free from its rendered markdown), `customer_flags`, `customer_health(score, components, computed_at)`.

Read tools  
crm.get_customer_360, crm.get_health_score (fuses payment behaviour, order rhythm, support sentiment — three signals no single tool holds), crm.get_segments, crm.get_next_best_action, customers.get_changes / movement **Built**.

Action tools  
crm.merge_entities (writes; auto when the match is exact, confirm otherwise) · crm.log_interaction (auto) · memory.save_fact.

Watchers  
Health recompute on every relevant event · At-risk crossing → `customer.at_risk` to Sales and Strategy · Duplicate detection after each sync.

Gate  
Logging and scoring auto; merges confirm unless exact; outbound anything goes through the owning field's tools.

Status  
**Partial** — customer master, summaries and contacts exist; resolution across sources and the health score are next, and become urgent the moment a second source (Tally, Zoho, a sister company) shares customers.

Field 6

### Order Tracking

**Owns** the journey from won deal to delivered goods.

Data in  
Sales orders with delivery dates and dispatch status (TranzAct \#2) **Built**; production status (#25); dispatch and e-way bill events once BIDE or Tally issues them; transporter status later.

Stored as  
`canon_sales_order` **Built**; `order_milestone(order_ref, milestone, at, source)` and `order_eta`.

Read tools  
orders.get_book_summary, orders.get_overdue **Built**; orders.get_status(order), orders.get_eta_risk (delivery date vs WIP and stock), orders.get_fill_rate.

Action tools  
orders.draft_customer_notice (writes; bad news → confirm) · orders.flag_delay (writes; alerts ops) · orders.trigger_invoice (writes → Finance; the order-to-cash synapse).

Watchers  
ETA at risk → ops alert · Milestone reached → proactive notice draft · Dispatched → invoice draft to Finance · Overdue undelivered → Pulse.

Gate  
Status and alerts auto; customer notices confirm (good news graduates to auto); invoice creation follows Finance's rules.

Status  
**Partial** — book and overdue reads exist; milestones and ETA need production and dispatch signals joined.

Field 7

### Inventory

**Owns** the right stock, in the right quantity, at the right time.

Data in  
Stock valuation snapshot (TranzAct \#9), GRN/QIR (#34), sales and purchase lines for velocity **Built**; Tally stock items and stock vouchers (§9); a true stock ledger where the source has one.

Stored as  
`canon_inventory_item`, `canon_grn` **Built**; `stock_daily_snapshot`; `sku_class(abc, velocity, reorder_point, lead_time_days)`; cost per SKU as a dated `memory_fact` until a cost source exists.

Referenced by  
`sku:CODE`, `vendor:CODE`, `grn:NUMBER`. Facts: `unit_cost`, `preferred_vendor`, `min_order_qty`, `is_seasonal`.

Read tools  
inventory.get_summary / by_category / top_holdings / dead_stock / reorder_alert / turnover, grn.get_summary **Built**; inv.get_stockout_risk (forecast vs cover), inv.get_abc, inv.suggest_vendor (last vendor, last price, lead time), inv.get_dead_stock_delta.

Action tools  
inv.create_draft_po (writes; money-gated above a limit) · inv.flag_trapped_capital (writes → Strategy) · inv.flag_integrity_issue (negative or impossible stock → human).

Watchers  
Days of cover below threshold → draft PO · Dead-stock delta up → Strategy flag + Stock-Push audience to Marketing · Negative stock → integrity flag · Demand forecast refresh → Production.

Gate  
Flags auto. Draft POs confirm; above the owner's money threshold, human. Nothing is ever ordered automatically.

Status  
**Built** reads; **To build** the draft-PO action and the snapshots; **Needs data** for true turnover and GMROI (a stock ledger, costs).

Field 8

### Production & QA

**Owns** making the thing, and making it right.

Data in  
Process details / work orders (#25), routing and BOM (#86), GRN inspection (#34) **Built**; later shop-floor telemetry, machine logs, vision inspection.

Stored as  
`canon_production`, `canon_routing` **Built**; `canon_work_order(status, planned_qty, produced, rejected, station, started, due)`, `quality_event`.

Read tools  
production.get_summary / wip / bom_coverage **Built**; prod.get_reject_trend (drift vs trailing), prod.get_capacity (load vs demand from the order book), prod.get_material_shortfall (BOM × open orders vs stock).

Action tools  
prod.draft_schedule (writes; planner confirms) · prod.flag_quality_drift (writes → QA, R&D) · prod.request_material (writes → Inventory draft PO).

Watchers  
Reject rate drift → alert · Material shortfall against open orders → request · Capacity overload → Strategy · Work order late → Orders ETA risk.

Gate  
Monitoring auto; schedules and material requests confirm; anything touching machines (maintenance halts) human until telemetry exists.

Status  
**Partial** — counts and coverage exist; scheduling and material planning need BOM explosion against the order book, which is buildable on synced data.

Field 9

### People Management

**Owns** the team — the field that needs the most care, and where the dangerous parts are deliberately human.

Data in  
An HR or attendance source (biometric export, payroll software, a spreadsheet upload), leave requests through the app, policies as documents in the knowledge plane.

Stored as  
`canon_employee`, `attendance_event`, `leave_request`, policies as `knowledge_source(kind='policy')`. Compensation is stored encrypted and read only by payroll tools with the money gate.

Read tools  
people.get_headcount, people.get_attendance_anomalies, people.get_leave_balance, docs.search(policy).

Action tools  
people.draft_onboarding_checklist (writes → Technology for access) · people.approve_leave (auto when balance and coverage allow) · payroll.compute (writes; disbursement is moves_money → human) · people.draft_jd, people.rank_resumes (assist only; never decides).

Watchers  
Attendance anomaly → supervisor · Payroll cycle → compute → human · Policy question → helpdesk answer from the knowledge plane.

Gate  
Leave within policy auto. Anything about pay, ratings, hiring or firing: human. Engagement signals are private to HR.

Status  
**Needs data** and the knowledge plane; Stage 3+.

Field 10

### Legal

**Owns** keeping the company safe on paper.

Data in  
Contracts, supplier terms, NDAs, licences, regulatory notices — uploaded documents; obligation dates extracted from them.

Stored as  
`canon_contract(counterparty_ref, type, start, end, renewal, value, risk_score)` with the document chunked and embedded in the knowledge plane; `contract_obligation(due, kind, status)`.

Read tools  
legal.get_expiring, legal.extract_clauses (model over the chunks; result stored, never re-derived), docs.search, legal.get_counterparty_terms (bridges to `customer:`/`vendor:` — payment terms from a contract become a memory fact).

Action tools  
legal.draft_from_template (writes; non-standard → counsel) · legal.flag_risk (writes) · legal.alert_obligation (writes).

Gate  
Sign-off is always human. Drafts and flags confirm.

Status  
**Needs data** — the knowledge plane and a document intake; Stage 3+.

Field 11

### R & D

**Owns** knowing the market and shaping what comes next.

Data in  
Internal evidence first: lost-deal reasons (Sales), ticket themes (Support), reject and yield data (Production), cross-sell gaps (Marketing). External: web research and competitor pages via external tools, stored in the knowledge plane.

Stored as  
`need_backlog(need, evidence_refs[], votes, status)`, `knowledge_source(kind='research')`, `battlecard`.

Read tools  
rd.mine_needs (clusters tickets + lost reasons), rd.get_backlog, rd.get_competitor_brief, prod.get_reject_trend.

Action tools  
rd.draft_brief (writes) · rd.update_battlecard (writes → Sales) · rd.propose_concept (writes; feasibility and cost from Production).

Gate  
All confirm; decisions human.

Status  
**To build**; needs Support and lost-reason capture first, then the knowledge plane.

Field 12

### Strategy & Planning

**Owns** direction — the apex that consumes every other field and feeds targets back down.

Data in  
Everything, read through the other fields' tools. Targets set by the owner (`kpi_target(metric, period, value)`). For Vinayak: the group layer (§3.7).

Stored as  
`kpi_target`, `experiment(hypothesis, action_refs[], metric, start, result)`, review packs as generated documents in the knowledge plane.

Read tools  
strat.get_kpi_vs_target, strat.get_working_capital (inventory + AR − AP, and its drift), strat.get_concentration_trend, strat.get_group_overview (per company: cash view, overdue, drift, what changed), strat.get_trapped_capital.

Action tools  
strat.draft_review_pack (writes; the Monday one-pager and the monthly board pack) · strat.propose_experiment ("₹X dead stock → clearance test"; writes) · strat.cascade_targets (writes targets down).

Watchers  
KPI off-track → alert + explanation (why_changed) · Weekly review pack · Concentration or working-capital drift → flag.

Gate  
Recommends; a human decides. Everything confirm.

Status  
**Partial** — the handlers exist as chat intents; the review pack, targets and the group page are the build.

Field 13

### Technology

**Owns** keeping the brain alive — the caretaker, not a peer field.

Data in  
`tz_sync_runs`, `ingest_issues`, `brain_runs`, connector health, the Tally bridge heartbeat (§9), cost per call.

Read tools  
meta.get_data_freshness, meta.get_ingest_quality **Built**; tech.get_connector_health, tech.get_cost_report, tech.get_eval_status.

Action tools  
tech.alert_stale_data (writes; badges every card) · tech.provision_access (writes ← People; sensitive → human) · tech.pause_watcher (writes; the kill switch).

Watchers  
Report older than its freshness bound → `data.stale` · Bridge heartbeat missed → alert the site · Ingest issue pattern repeats N times → engineering ticket to write a deterministic mapper · Cost per question above budget → throttle.

Gate  
Alerts auto; security actions human, never automated.

Status  
**Partial** — sync health and ingest quality exist; the watchdog and bridge monitoring come with the worker.

## 8 · How the fields become one brain

Thirteen fields with their own tools would be thirteen bots. What makes them one brain is that they share a canonical model (so a customer is the same customer everywhere), share one memory (so what the owner taught Finance is known to Sales), and are wired by events (so a change in one field wakes a workflow in another with no human relaying it).

    EVENT invoice.overdue {customer: "Dev Colour", amount: 420000, rung: 3}
      → Finance   : confirm the pattern is worsening; draft R3 chase        [confirm]
      → Sales     : STOP verdict; badge on quotes/orders; pause upsell       [auto badge, human hold]
      → CRM       : health score down; 360 updated                          [auto]
      → Marketing : remove from Reorder/Cross-sell audiences                 [auto]
      → Strategy  : concentration + exposure line in the weekly review       [auto]
    ONE event, FIVE fields, no relay.

### The event catalogue

| Event                                | Emitted by            | Consumed by                                                          | Synapse                                  |
|--------------------------------------|-----------------------|----------------------------------------------------------------------|------------------------------------------|
| `invoice.overdue{rung}`              | Finance rung detector | Collections, Sales credit, CRM health, Marketing audiences, Strategy | 1 · Accounts → Sales — **first to ship** |
| `promise.broken`                     | Finance               | Collections escalation, Pulse                                        | 1                                        |
| `credit.flagged`                     | Sales credit gate     | Quotes/orders UI, quote generation                                   | 1                                        |
| `collection.chased`                  | Executor              | CRM interaction log, episodic memory                                 | —                                        |
| `customer.quiet` / `customer.lapsed` | Marketing scans       | Reorder, Win-back drafts; CRM                                        | —                                        |
| `stock.low` / `capital.trapped`      | Inventory             | Draft PO; Sales ATP; Strategy; Marketing push                        | 5 · Inventory + Accounts → Strategy      |
| `order.dispatched` / `order.delayed` | Orders                | Finance invoice, CRM, Support, customer notice                       | 3 · Sales → Inventory → Production       |
| `quality.drift`                      | Production QA         | R&D, Support                                                         | 2 · Support → R&D / QA                   |
| `customer.at_risk`                   | CRM health            | Sales, Strategy                                                      | 6 · Support + CRM + Accounts → churn     |
| `deal.lost{reason}`                  | Sales                 | R&D backlog, Marketing                                               | 4 / 7                                    |
| `data.stale`                         | Technology watchdog   | Every card, engineering                                              | —                                        |

### Why one loop, not thirteen

Because every workflow above is the same six beats, a new synapse is a new event type plus a new watcher row. It adds no control flow, no new gate, no new memory rule. The eval harness grows a case per watcher, and the ledger records every action identically whether it came from Finance or Production. That is the guarantee the reference's Part 1A makes — bringing a field online is edge work — and it is what lets the brain get denser without getting more dangerous.

### The multi-agent question

When several synapses fire from one event, today's design runs them as separate passes through the one runtime, in order, sharing the ledger. That is correct and sufficient until two passes need to negotiate (Sales wants to quote; Finance wants to hold) or a workflow needs durable state across days (a chase ladder with pauses). At that point a supervisor pattern — one coordinating pass that calls field-scoped sub-passes as tools — is the natural next step, and it is exactly the case where an orchestration framework behind the `AgentRunner` port earns its place. The gate stays ours either way.

## 9 · Connecting Tally on an offline computer

Tally is the biggest footprint in Indian SMB accounting and the hardest integration: it is a desktop application, its data file lives on one Windows PC in the accounts room, that PC is often on a LAN with no reliable internet, and the company file must be open in Tally for anything to read it. There is no cloud REST API. What Tally does offer, and has for years, is an XML-over-HTTP gateway on the machine itself.

### 9.1 What Tally exposes

- **The XML gateway.** With `ServerPort=9000` in `tally.ini` and connectivity set so TallyPrime "acts as both client and server", Tally answers HTTP POSTs on `http://127.0.0.1:9000` (or its LAN address) while a company is loaded. Requests are XML envelopes. `Export` requests with a `Collection` pull masters and transactions (Ledger, Group, StockItem, Voucher, Bills, VoucherType, Currency) with a `FETCH` list of fields and `SVFROMDATE`/`SVTODATE` filters. `Import Data` requests create or alter masters and vouchers.
- **Incremental extraction.** Every master and voucher carries an `ALTERID`, a monotonically increasing edit counter, so a pull of "everything with `ALTERID` greater than the last one I saw" is the incremental sync; deleted vouchers are detected by comparing the id set.
- **ODBC and TDL.** ODBC suits one-off pulls into Excel; TDL (Tally's own language) can add menus, custom fields and reports inside Tally. Neither is needed for reading; TDL is used only if an operator must trigger a sync from inside Tally, and every line of it is a line that can break on a Tally update.
- **Known rough edges.** Output is nominally UTF-8 but contains Windows-1252 bytes and illegal entities; symbols such as ₹ come out as `?`; asking for full ledger-entry trees turns a few thousand vouchers into a hundred-megabyte response. The mapper decodes tolerantly, fetches only the fields it needs, and pages by date range.

### 9.2 The Tally Bridge

Because Tally cannot call out and the PC may be offline, BIDE ships a small agent that runs on the LAN and does the calling. It is the only BIDE component that runs on customer premises, and it is built to be boring.

**What it is**A signed Windows service (Python packaged as a single .exe, or Go) installed on the Tally PC or any LAN machine. No UI beyond a tray icon and a status page on localhost.

**Pairing** Installed with a one-time pairing code from the BIDE workspace. The bridge holds a device certificate; the cloud knows which workspace and which Tally company names it may sync. Nothing else on the network is reachable to it.

**Pull** On a schedule (every 15 minutes while Tally is open) it POSTs Export envelopes to port 9000: first masters (Ledger with parent group, opening/closing balance, address, GSTIN; StockItem with unit, rate, closing qty and value; Group; VoucherType), then vouchers since the last `ALTERID` in date pages, then Bills (outstanding receivables and payables with bill dates and reference).

**Buffer** Everything is written to a local SQLite queue as compressed, content-hashed batches. If the internet is down the queue grows; when it returns the bridge drains it in order. The bridge never loses a batch and never blocks Tally.

**Push** Batches go to `POST /ingest/tally` over TLS with the device certificate. The cloud lands them in `ty_*` raw tables keyed on `(company_id, raw_id)` exactly like every other source, runs the Tally mapper into canonical, and rebuilds.

**Write-back**When BIDE becomes the system of engagement (§10) the same bridge carries the other direction: approved vouchers queued in the cloud are pulled by the bridge and posted with `Import Data`, masters first, every voucher balanced, the BIDE id embedded in the narration and recorded in a sync ledger so nothing is ever posted twice.

**Health** Heartbeats every few minutes carry Tally version, open company, last `ALTERID`, queue depth. Missed heartbeats become a `data.stale` event and an alert to the site contact — "Tally is closed on the accounts PC" is by far the most common failure and it needs to be said in those words.

### 9.3 The Tally mapper

Tally's model is ledgers and vouchers, not invoices and customers, so the mapper does more work than TranzAct's. Sundry Debtors ledgers become `canon_customer`; Sundry Creditors become `canon_vendor`; Sales vouchers (with their inventory allocations) become `canon_sales_invoice` + lines; Purchase vouchers become purchase invoices; Receipt vouchers with `Agst Ref` bill allocations become payments against specific invoices — which is exact receipt data, something TranzAct never gave us; Bills outstanding become AR and AP with ages; StockItems become inventory; Journal and Payment vouchers become GL entries. Everything that will not map — a voucher whose party is a cash ledger, a bill reference that matches nothing — goes to `ingest_issues`. After the first three or four Tally companies the recurring patterns get deterministic mappers, per the hardening rule.

Tally is the source that unlocks deep finance: real payment dates (true DSO, behaviour scoring), AP aging (DPO, cash-conversion cycle), the GL (statements, GST reconciliation), and costs where the company keeps them. For Vinayak companies that run Tally alongside TranzAct, the same customer resolves across both through `canon_entity_alias`, and Finance reads the union.

### 9.4 When there is no PC to install on

Some sites will have Tally on a machine nobody may touch, or an accountant who works from a pen drive. The fallback is file-based: a scheduled Tally export (XML or the daybook) dropped in a watched folder, a shared drive, or emailed to a per-workspace address. The same mapper consumes it; freshness is simply lower and the card says so. Busy follows the identical pattern — a bridge speaking Busy's own interface, mapping into the same canonical objects.

## 10 · Becoming the ERP

Today BIDE mirrors a source. The end state you have described is that a company runs on BIDE: raises its quotes, orders, invoices and POs in it, and treats TranzAct or Tally as history — or as nothing at all. That is a real product and a much larger one than a mirror, so it is staged so that every stage is useful on its own and none of them requires a leap of faith from an accountant.

### 10.1 What a system of record must do that a mirror does not

- **Originate transactions** with statutory correctness: GST-compliant tax invoices (place of supply, HSN, rates, reverse charge), e-invoicing through the IRP for companies above the turnover threshold (IRN and QR on the invoice), e-way bills for movement, credit and debit notes, sequential numbering per series per financial year, cancellations with reasons and audit trail.
- **Hold masters** the business owns: customers and vendors with GSTIN and addresses, items with HSN and units, price lists, tax configurations, numbering series, bank accounts.
- **Keep the books**: a double-entry ledger, or a clean, complete feed into one; period locking; statements; GST return preparation and reconciliation against the portal.
- **Print and send** the documents in the formats customers, transporters and auditors expect.
- **Work in the room**: multi-user with roles, fast on a modest PC, usable when the internet drops mid-invoice, with a paper trail an auditor accepts.

The canonical model already has the right objects; what changes is that rows with `source = 'bide'` stop being copies and become originals, with the rules above enforced on write.

### 10.2 The four stages of a migration

1.
    **Mirror — read-only, weeks 0–4**Connect the source (TranzAct API, Tally bridge). Full history pulled; canonical reconciled to the source's own printed totals; Pulse, Inbox and Ask live on that data. The owner gains visibility and the collections loop without changing how anyone works. Exit test: every headline total reconciles, and the team uses it weekly.

2.
    **System of engagement — write upstream of the ledger, months 1–3**BIDE owns everything before a statutory document exists: leads, quotes, sales orders, purchase orders, GRNs, collections, promises, customer contacts. These are created in BIDE and, where the source can accept them, pushed back (Zoho REST; Tally `Import Data` via the bridge; TranzAct if and when it exposes writes). Invoicing still happens in the source, and BIDE ingests the result and matches it to its order. The source stays the ledger of record; BIDE is where the work happens. Exit test: no order or quote is keyed twice; write-backs reconcile.

3.
    **Parallel run — BIDE issues documents, the source keeps the books, months 3–6**BIDE raises tax invoices with numbering, GST, e-invoice IRN and e-way bill, prints them, and posts the balanced voucher to Tally (or Zoho) through the bridge the same day, so the accountant's world and the statutory returns are unchanged. Both systems carry every document; a nightly reconciliation flags any difference. Money still moves only from the source's payment run, approved by a human. Exit test: sixty consecutive days with zero unreconciled differences and no invoice cancelled for a BIDE error.

4.
    **Primary — BIDE is the system of record**Two honest options, chosen per company. *Option A, the pragmatic one:* BIDE is the operating system for everything and Tally remains the statutory ledger it posts to — the accountant and the CA keep the tool the audit and the GST filing already trust, and BIDE never has to become an accounting package. *Option B, full replacement:* BIDE carries its own ledger, GST return preparation and bank reconciliation; the source is archived with its history already in canonical. Option B is a Stage-4 product on the business plan's timeline and should be taken on only when several companies on Option A are asking for it.

### 10.3 What has to be built for each stage

| Stage      | Build                                                                                                                                                                                                                         | Reuses                                                                                       |
|------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| Mirror     | Tally bridge + mapper; reconciliation report against source totals                                                                                                                                                            | Everything that exists                                                                       |
| Engagement | Transactional screens for lead, quote, order, PO, GRN with the state machines; masters editing with validation; write-back executors per source with a sync ledger; role-based permissions                                    | Canonical objects, ledger, Inbox, tools                                                      |
| Parallel   | Invoice engine: numbering series, GST computation, HSN master, e-invoice (IRP API via a GSP), e-way bill API, print templates, credit/debit notes, cancellation; voucher posting to the ledger source; nightly reconciliation | Bridge write-back, action gate (issuing an invoice is a confirm action; cancelling is human) |
| Primary A  | Period locks; document-level audit trail; offline-tolerant entry (local queue in the browser); bank feed and cash application                                                                                                 | All of the above                                                                             |
| Primary B  | Double-entry ledger, trial balance and statements, GST returns and 2A/2B reconciliation, TDS, bank reconciliation, year-end close, auditor exports                                                                            | —                                                                                            |

### 10.4 How the brain rides along

Nothing in the agent changes when BIDE becomes the origin of a document. A quote drafted by Sales is proposed to the ledger, approved, and becomes a `canon_sales_quotation` with `source='bide'`; the same read tools see it. The gate is stricter for originals — an invoice is a confirm action, a cancellation is human, a payment run is human — and the episodic log becomes the audit trail an auditor reads. The difference for the owner is that the Inbox stops being "things the brain drafted from the ERP" and becomes "the company's work queue, with the brain having done the first pass".

The reference's own rule applies here more than anywhere: sell the outcome, build the platform. The first company that moves to Option A does so because the collections loop, the credit gate and one-screen quoting saved it money for six months — not because it was promised a new ERP.

## 11 · Rollout across Vinayak

Nine sister companies under one family are an unusual advantage: nine sets of real books, one sponsor, and users whose complaints reach you the same day. The rollout uses that.

### 11.1 Onboarding a company

1.
    **Workspace and sources**Create the workspace in the group; connect TranzAct with the company's credentials, or install the Tally bridge on the accounts PC and pair it. Choose history depth. Full migration runs in the background; Pulse fills as pages land.

2.
    **Profile** Ten minutes with the owner or accountant: industry, fiscal year, GST status, healthy margin, seasonality, key customers and their terms, the KPIs they actually watch. Every answer is a `memory_fact` or a profile field the brain uses from the first question.

3.
    **People and roles**Add each user with what they do — runs the company, runs the accounts, is the CA, runs sales — and two permissions: may approve outbound messages, may approve anything that moves money. Role seeds the dashboard layout (which cards are pinned and in what order) and nothing else; the user can rearrange. Permissions gate the Inbox.

4.
    **Contacts and costs**The accountant uploads two CSVs: customer email and WhatsApp numbers; cost per SKU with an as-of date. These unlock sends and margin respectively. Where Zoho or Tally is connected, both are pre-filled.

5.
    **Reconcile and switch on**Headline totals are reconciled against the source's own report; ingest issues reviewed; the first three watchers enabled (overdue rungs, data stale, anomalies) with the gate on confirm for everything. The daily brief starts the next morning.

### 11.2 The group view

For the family, the home screen is not a company's Pulse but the group: one row per company with its 30-day cash view, overdue, aging drift, what changed this week, and the count of items waiting in its Inbox, sorted by who needs attention; a group cash line and a group exposure line at the top; cross-company facts the companies themselves cannot see — a customer owing three of them at once, a vendor supplying four at different prices, intercompany balances to net. Drilling into a row lands on that company's Pulse. Group reads are unions over member workspaces through the same tools, so a group CFO asking "who owes us the most across the group" is one question through one door.

### 11.3 Order of companies

Start with the company whose TranzAct data is cleanest and whose owner makes a recurring monthly decision — that is the reference's sandbox rule and it still holds. Second, the company that runs Tally, because it proves the bridge and the second mapper. Third, one that shares customers with the first two, because it proves entity resolution and the group view. The remaining six are then configuration. Each company graduates from mirror to engagement on its own evidence: the owner is opening it three or more days a week and at least seven in ten drafts go out unedited.

### 11.4 The numbers that decide the next step

| Number                                        | What it tells you                                                            |
|-----------------------------------------------|------------------------------------------------------------------------------|
| Companies using it weekly                     | Whether the pain is real and recurring                                       |
| Drafts approved without edits, per watcher    | Whether the brain is good enough to graduate                                 |
| Days-to-get-paid before vs after, per company | The number that sells the next company — inside the group and outside it     |
| Citation compliance and action-eval pass rate | Nothing shipped that can state an uncited number or act where it must refuse |
| Cost per question, per brief                  | The product is not getting better by getting expensive                       |
| Days of our time per new company              | Whether this is a product or a consulting engagement                         |

### 11.5 Then productise

When the nine companies run on the same code with differences only in settings, the product exists. The business plan's wedge — TranzAct manufacturers, then Tally users, sold on collections and credit, priced per company — is unchanged; what Vinayak adds is nine reference customers whose before-and-after numbers are your own.

## Glossary

| Term                         | Meaning here                                                                                                                              |
|------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| Adapter                      | Code that pulls one source (TranzAct, Zoho, Tally) into raw tables and maps it into canonical. The moat.                                  |
| Canonical model              | The one source-independent schema every layer above the adapter speaks.                                                                   |
| Entity reference             | The `type:code` string every store uses to point at a customer, invoice, SKU, lead, ticket, contract.                                     |
| Evidence / claim             | A retrieved number with an id; a statement that must cite evidence to assert a number.                                                    |
| Tool                         | A function the model may call, declared against the contract with a side-effect class and quality signals.                                |
| Read / action / compose      | Read tools run inline. Action tools propose to the ledger. Compose is the pure part of an action tool that builds the payload.            |
| Gate / authorizer            | Deterministic rules deciding auto / confirm / human from side effect, quality and history. Never the model.                               |
| Numeric guard                | The check that every rupee figure in text or a payload matches evidence exactly.                                                          |
| Watcher / workflow           | A declarative row: trigger, detector, gather tools, compose tool, gate policy, cooldown.                                                  |
| Event / synapse              | A typed event on the bus; a cross-field flow where one field's event wakes another's workflow.                                            |
| Ledger (`actions`)           | Every proposal, decision, execution and outcome.                                                                                          |
| Episodic log (`brain_runs`)  | Every pass of the loop: trigger, tools, evidence, decision, outcome, cost.                                                                |
| Harness                      | The eval suite that ship-blocks a release on an uncited number, a banned phrase, or a wrong action.                                       |
| AgentRunner                  | The port behind which the orchestration engine (native loop today, ADK or LangGraph later) lives.                                         |
| MCP                          | Model Context Protocol — the transport that publishes the tool registry to external clients, and by which BIDE consumes external servers. |
| Bridge                       | The on-premises agent that reads and writes Tally over its XML gateway and relays through a buffered queue.                               |
| Mirror / engagement / record | The three postures of BIDE toward a source: copy it, own the work upstream of it, be the origin.                                          |

Architecture, layer statuses and tool names are read from the codebase and the BIDE reference at the time of writing. Tally integration facts are from Tally Solutions' integration documentation and current developer guides; verify the exact TallyPrime release behaviour on the target machines before shipping the bridge. Formulas for Finance cards are quoted from `docs/V0_FINANCE_SPEC.md`.
