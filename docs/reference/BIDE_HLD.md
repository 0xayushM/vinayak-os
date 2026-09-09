# BIDE High-Level Design

> v1, September 2026. Diagrams are inline SVG and do not render on GitHub — open `BIDE_HLD.html` in a browser for the figures; the text and tables below are complete.

The system-level design of the Business IDE: what the parts are, how they talk, where data lives, what a request and a background pass move through, how sources plug in, where the trust boundaries sit, and the decisions that shape all of it.

**Companion documents** BIDE Build Reference (mechanism detail per field) · BIDE Stage Review (status and gaps) · The Business IDE reference (product rationale)

## 1 · Scope and quality goals

**In scope.** A multi-tenant platform that ingests a company's operating data from its ERPs and other sources, normalises it into one canonical model, serves a decision-oriented dashboard, answers questions with cited, confidence-labelled numbers, runs background watchers that prepare actions, and executes approved actions through outbound channels and write-backs. Group-level views across sister companies. Adapters for TranzAct, Zoho Books and Tally (via an on-premises bridge).

**Out of scope for v1.** Being the statutory ledger (BIDE posts to one; §7.4 of the Build Reference stages the path); real-time shop-floor telemetry; a self-serve onboarding flow.

| Quality goal     | Target                                                                        | How the design meets it                                                                                                           |
|------------------|-------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------------------|
| Numeric honesty  | 0 uncited money figures shipped, ever                                         | Numbers only from deterministic queries; numeric guard on every model output; eval ship-gate in CI                                |
| Safe autonomy    | Money and regulator actions never execute without a human                     | Side-effect classes on every tool; deterministic gate; ledger with idempotency; autonomy earned per watcher from approval history |
| Tenant isolation | No cross-workspace read or write                                              | `company_id` injected by the layer on every query; model never chooses it; allowlist-based auth                                   |
| Freshness        | Hourly for API sources, 15 min for Tally while open; staleness always visible | Scheduled incremental syncs; per-panel freshness envelope; `data.stale` event                                                     |
| Resilience       | A failed sync never blanks data; a failed model call never fails a request    | Upsert-only writes; deterministic engine as fallback; buffered bridge queue                                                       |
| Auditability     | Every number and every action traceable                                       | Raw rows kept forever; provenance on canonical rows; episodic log of every pass                                                   |
| Cost             | Cost per question tracked and bounded                                         | Pre-aggregated tool outputs; two model tiers; cached prompt prefix; deterministic detectors before any model call                 |

## 2 · System context

\*\[Figure: System context: five kinds of users on the left use BIDE in the centre; BIDE reads from TranzAct, Zoho and Tally (through a bridge), calls the Claude model, sends through email and WhatsApp providers, and exposes tools to MCP clients.\]\* Everything on the right is pulled from or pushed to by BIDE; nothing external calls into BIDE except the Tally bridge (an on-premises BIDE component) and, later, MCP clients.

Users interact through the web app and, for the morning brief, through WhatsApp or email. Sources are read by pull on a schedule (TranzAct and Zoho over the internet; Tally over its LAN gateway via the bridge). The model is called only by the agent runtime and only with tool schemas and capped evidence. Outbound channels are reached only by executors after a human decision. External clients reach the tool registry over MCP in a later stage.

## 3 · Containers

\*\[Figure: Container view: browser talks to the Next.js BFF on Vercel; the BFF forwards with internal key and workspace id to the FastAPI API on Railway; API and worker share Supabase Postgres; the worker runs syncs, detectors, watchers and the daily brief; the Tally bridge on premises pushes batches to the API; the model and outbound providers are called by the shared code in API and worker.\]\* Two processes share one package: the API answers requests, the worker does everything that is scheduled or event-driven. The bridge is the only component outside the cloud and the only external thing that calls in.

| Container    | Technology                                  | Responsibility                                                                                                     | Talks to                           |
|--------------|---------------------------------------------|--------------------------------------------------------------------------------------------------------------------|------------------------------------|
| Web app      | Next.js 16, React 19, Tailwind 4, SWR       | Dashboard, Pulse, Inbox, Ask, Settings, onboarding; per-role layouts                                               | BFF only                           |
| BFF          | Next.js route handlers, `@supabase/ssr`     | Session gate; forward with Bearer token, internal key, workspace id; never exposes backend URL                     | API                                |
| API          | FastAPI, Python 3.11                        | Token verification, allowlist, tenancy; panels; Ask; ledger decisions; connections; ingest endpoint for the bridge | Postgres, model, executors         |
| Worker       | APScheduler in-process now → Celery + Redis | Hourly syncs, canonical rebuild, snapshots, detectors, event consumption, watchers, daily brief, executors         | Postgres, sources, model, channels |
| Database     | Supabase Postgres, pgvector later           | All seven stores; RLS not relied on — the API enforces tenancy                                                     | —                                  |
| Tally Bridge | Signed Windows service, SQLite queue        | Pull from Tally over XML, buffer, push; later write-back                                                           | Tally :9000, API                   |
| Model        | Anthropic API behind `ModelPort`            | Tool-use turns, routing, phrasing; two tiers                                                                       | —                                  |
| Channels     | Resend/SMTP; WhatsApp BSP                   | Deliver approved messages; delivery receipts back to the ledger                                                    | —                                  |

## 4 · Components

Inside the shared package, dependencies point one way only. Nothing below imports something above it, which is what allows a source, a tool, a runner or the model to change without touching the core.

\*\[Figure: Component layering from bottom to top: config and domain; database gateway; adapters and canonical builders; query repository and service; memory, tools, model port; safety spine and reasoning engine; agent runtime with runners and watchers; API routes, worker jobs, eval harness. Arrows show imports pointing downward only.\]\* Highlighted components are the swap points: the runner port, the safety spine and the tool contract are the seams that let orchestrator, model and sources change without touching the rest.

| Component          | Responsibility                                                                       | Key interface                                                            |
|--------------------|--------------------------------------------------------------------------------------|--------------------------------------------------------------------------|
| adapters           | Authenticate, fetch, paginate, throttle, back off; land raw rows                     | `fetch_report()` / `fetch_all()`; bridge ingest handler                  |
| canonical          | Rebuild canonical objects from raw; log unmappables; refresh summaries and snapshots | `rebuild_canonical(conn, company_id)`                                    |
| query              | Typed, capped, company-scoped aggregations; the only read path for panels and tools  | ~60 functions on `QueryService`                                          |
| tools              | Declare tools; validate inputs; execute reads; propose non-reads to the ledger       | `Tool`, `ToolResult`, `execute(ctx, tool, args)`                         |
| memory             | Profile, facts (supersede/decay), summaries, threads, episodic log                   | `write_fact`, `active_facts`, `refresh_customer_summaries`, `record_run` |
| model              | Provider-agnostic chat with tools, tiers, caching                                    | `ModelPort.chat(system, messages, tools)`                                |
| reasoning/safety   | Grounding, numeric guard, confidence, fallback text                                  | `grounded()`, `confidence()`, `safe_summary()`                           |
| agents             | Run a trigger through the loop with a chosen runner; apply the gate                  | `AgentRunner.run(conn, company_id, trigger, context)`                    |
| workflows          | Watcher definitions, SQL detectors, event types, cooldowns                           | `detect(company_id) → events`; `consume(event)`                          |
| ledger / executors | Propose, decide, execute, record outcome; channels and write-backs                   | `propose()`, `decide()`, `execute()`                                     |

## 5 · Data architecture

Seven stores with different write rules, all in one Postgres, all keyed by `company_id` and joined through the entity reference `type:code`.

\*\[Figure: Data flow between the seven stores: sources land in raw tables; a rebuild derives canonical tables and flat views, which in turn refresh entity summaries and daily snapshots and feed detectors; detectors write events; watchers read canonical, memory and history and write proposals to the actions ledger; executions write outcomes back to actions and to the episodic log; owner corrections write memory facts; the knowledge plane sits apart and meets the rest only at the tool interface.\]\* Raw is the only store a source writes; everything else is derived or written by BIDE itself. Money figures come from stores 2 and 6 only; the knowledge plane can never be the source of a number.

| Store          | Tables                                                                                                                                               | Write rule                                                                                                                                           | Retention                                              |
|----------------|------------------------------------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------|
| 1 Raw          | `tz_*`, `zb_*`, `ty_*`                                                                                                                               | Upsert on `(company_id, raw_id)`; never truncate                                                                                                     | Forever                                                |
| 2 Canonical    | `canon_*`, `canon_*_flat`, `canon_entity_alias`, `ingest_issues`                                                                                     | Rebuilt from raw after every sync; upsert on `(company_id, source, source_ref)`; `source='bide'` rows are originals written by transactional screens | Forever                                                |
| 3 Memory       | `business_profile`, `memory_fact`, `entity_summary`, `chat_thread`, `chat_turn`                                                                      | Facts supersede; stale on expiry or contradiction; summaries refreshed after rebuild                                                                 | Forever (superseded kept)                              |
| 4 Bus & ledger | `events`, `actions`, `customer_flags`, `campaigns`, `campaign_targets`                                                                               | Events idempotent by key; actions append with status transitions; flags upserted per entity                                                          | Events pruned after processing + 90 d; actions forever |
| 5 Episodic     | `brain_runs`                                                                                                                                         | Append-only                                                                                                                                          | Forever (compressed after 1 y)                         |
| 6 History      | `ar_daily_snapshot`, `ap_daily_snapshot`, `stock_daily_snapshot`, `pipeline_daily_snapshot`                                                          | One insert batch per day per company                                                                                                                 | Forever (rows are tiny)                                |
| 7 Knowledge    | `knowledge_source`, `knowledge_chunk`, `knowledge_node`, `knowledge_edge`                                                                            | Chunked and embedded on upload; deduped by content hash                                                                                              | Until the owner removes the source                     |
| Platform       | `companies`, `groups`, `group_members`, `users`, `user_layouts`, `tool_connections`, `workflows`, `tz_sync_runs`, `tz_sync_cursor`, `bridge_devices` | Administrative                                                                                                                                       | —                                                      |

**Referencing.** Every store that points at a business thing does so with `entity_ref = type:code` using the canonical code, so a join across invoices, facts, tickets, actions and episodes is one equality. `canon_entity_alias` maps every source's spelling to that code, within a company and across a group.

## 6 · Runtime views

### 6.1 A question

\*\[Figure: Sequence for a question: browser posts to BFF; BFF forwards to API with token, key and workspace; API resolves tenancy and loads context from memory; runtime calls the model with tool schemas; model requests tools; executor runs queries and returns evidence; model writes an answer; safety spine checks grounding and sets confidence; API saves the turn and returns.\]\* The model sees tool schemas and capped tool results, never the database. If the model is unavailable or a figure fails the guard twice, the deterministic engine answers from the same tools.

### 6.2 A background pass

\*\[Figure: Sequence for a background pass: sync lands raw rows; rebuild derives canonical and snapshots; detectors emit events; the worker consumes an event, runs the watcher through the runtime which gathers evidence and composes a draft under the guard; the gate decides confirm; a proposal is written to the ledger and the owner is notified; on approval the executor sends and records the outcome and episode.\]\* Detection is deterministic SQL and costs nothing; the model is invited only after something has been detected, and only to word a draft that the guard then checks. The approval history feeds the gate's autonomy ladder.

### 6.3 The gate

\*\[Figure: Gate decision: a proposed action enters; if side effect is money or regulator it always routes to human; otherwise if data is stale or the entity is unresolved it escalates; otherwise if the watcher's approval history has earned auto it runs after a cancellable hold; otherwise it waits for confirm in the inbox.\]\* Three questions in a fixed order. The first is answered by the tool's declared class, not by anything the model said; a rejection at any watcher demotes it back to confirm.

## 7 · Integration

Every source implements one contract — extract, map, load — and lands in raw before anything else touches it. The difference between sources is only where the extraction runs.

\*\[Figure: Three adapter shapes side by side: TranzAct and Zoho are pulled by the cloud worker over HTTPS; Tally is pulled by the on-premises bridge over its LAN XML gateway, buffered in a local queue, and pushed to the cloud; CSV and email drops are watched folders or mailboxes. All three land in raw tables and share one mapper contract into canonical.\]\* Only the extraction step differs: a cloud API is pulled from the worker, Tally is pulled on premises and relayed, files are watched. From raw onward the path is identical.

| Integration       | Direction               | Mechanism                                                                                                  | Status           |
|-------------------|-------------------------|------------------------------------------------------------------------------------------------------------|------------------|
| TranzAct          | Read                    | Reporting API, report ids resolved via catalogue, 8 req/min, page-walk with cursor                         | **Built**    |
| Zoho Books        | Read; write later       | REST v3 with OAuth refresh token; contacts, items, invoices, bills, payments                               | **Partial**  |
| Tally             | Read; write later       | On-prem bridge → XML gateway; incremental by `ALTERID`; `Import Data` for write-back                       | **To build** |
| CSV / email drop  | Read                    | Upload screen, watched mailbox; same mapper                                                                | **To build** |
| Email out         | Write                   | Resend or SMTP; executor only                                                                              | **Built**    |
| WhatsApp          | Write; read for support | Business API via a BSP; DLT registration                                                                   | **To build** |
| Model             | Call                    | Anthropic API via `ModelPort`; tools-only                                                                  | **Built**    |
| MCP               | Serve; consume          | Registry published as an MCP server with per-client scopes; external MCP servers wrapped as external tools | **To build** |
| e-Invoice / e-Way | Write                   | GSP APIs to the IRP and e-way bill system; needed only when BIDE issues invoices                           | **Stage 3**  |

## 8 · Security and tenancy

\*\[Figure: Trust boundaries: browser holds only a Supabase session; the BFF holds the internal key and backend URL; the API verifies the token, checks the users allowlist, resolves and authorises the workspace, and injects company_id into every query; the database is reached only by API and worker; the bridge authenticates with a device certificate; secrets for sources are Fernet-encrypted at rest; the model receives no credentials and no raw rows.\]\* Five checks in the API, in order, on every business request. Nothing downstream of the API re-derives tenancy; nothing upstream holds a secret it does not need.

- **Authentication.** Supabase Auth issues sessions; the API verifies access tokens (HS256 secret or JWKS) and treats the `users` table as an allowlist — a valid account with no row is denied.
- **Authorisation.** Role (owner / finance / accountant / sales / viewer) plus two explicit permissions: *may approve outbound messages*, *may approve money*. The Inbox and the decide endpoint check them. Group membership grants read across member workspaces only.
- **Tenancy.** `company_id` is a parameter of every query function and is supplied by `require_workspace`, never by the model or the browser. Group reads iterate the caller's authorised member set.
- **Secrets.** ERP credentials Fernet-encrypted in `tool_connections`, decrypted only in memory at sync time; platform secrets in environment; bridge devices hold a certificate scoped to one workspace and a named Tally company.
- **Model boundary.** The model receives the system prompt, tool schemas and capped tool results. It never receives credentials, raw rows, or another tenant's data, and it cannot choose a tenant.
- **Action safety.** Side-effect classes are declared in code, not inferred; the gate is deterministic; every send is idempotent and rate-capped; money and regulator actions have no auto path.

## 9 · Deployment and scaling

| Component    | Today                                          | Next                                                                        | Trigger to move                                                                              |
|--------------|------------------------------------------------|-----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| Web + BFF    | Vercel, one project                            | Same                                                                        | —                                                                                            |
| API          | Railway, one container, APScheduler in-process | Railway API + separate worker service; Celery + Redis                       | Sync or watcher runtime visibly competes with request latency, or a second replica is needed |
| Database     | Supabase direct connection                     | Supavisor pooled connections (H1); read replica (H5)                        | Connection exhaustion under concurrent panels; heavy detectors                               |
| Cache        | None (pre-aggregation)                         | Redis for KPI and Pulse endpoints (H2), invalidated on rebuild              | Repeated identical panel reads dominate DB load                                              |
| Model path   | Inline calls                                   | Per-tenant rate limits, queue for background passes, streaming for Ask (H6) | Cost or latency spikes                                                                       |
| Bridge       | —                                              | Signed installer; auto-update channel; per-site health                      | First Tally company                                                                          |
| Vector store | —                                              | pgvector in the same database                                               | First document-driven workflow (Support, Legal)                                              |

Vinayak's nine companies fit comfortably in the "today" column: syncs are rate-limited by the sources, not by us; detectors are SQL over tens of thousands of rows; the model is called only on detection or on demand. The first thing to break at outside-customer scale is Postgres connections, then in-process sync — both have named fixes above.

## 10 · Cross-cutting concerns

| Concern       | Design                                                                                                                                                                                                                                                               |
|---------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Observability | Structured logs with request id and company id; `tz_sync_runs` per pipeline; `brain_runs` per pass with tools, latency, tokens, cost; connector health and bridge heartbeats on the Sync page; alerts as `data.stale` events                                         |
| Release gate  | CI runs unit tests and the eval harness on every push; citation compliance must be 100%; action cases must pass; a watcher cannot be enabled for a workspace without its golden set                                                                                  |
| Freshness     | Every envelope carries `last_synced_at` and `stale`; every card shows it; tools carry `data_fresh` for the gate; hourly API pulls, 15-minute bridge pulls, daily snapshots                                                                                           |
| Idempotency   | Raw rows by content hash; canonical by `(company_id, source, source_ref)`; events by key; actions by `(tool, entity, rung)` in a window; sends by action id; write-backs by sync ledger                                                                              |
| Cost control  | Deterministic detectors before any model call; capped tool payloads; two tiers; cached prefix; per-call cost logged; per-tenant budget with throttling                                                                                                               |
| Degradation   | Source down → last data stands, marked stale · Model down → deterministic engine answers, watchers pause composing · Channel down → action stays approved, retry from Inbox · Bridge offline → queue grows, heartbeat alert · DB down → 503, nothing partial written |
| Data quality  | `ingest_issues` surfaced on the Sync page and to the CA before sign-off; recurring patterns become deterministic mappers                                                                                                                                             |
| Backups       | Supabase point-in-time recovery; raw tables make canonical rebuildable; bridge queue is durable on disk                                                                                                                                                              |

## 11 · Key design decisions

| Decision                                                                              | Alternatives considered                                           | Why this one                                                                                                                                                 |
|---------------------------------------------------------------------------------------|-------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Numbers only from deterministic queries; model may phrase, never compute              | Let the model read tables; let it do arithmetic over tool results | Honesty must be structural. A guard can verify a figure exists; it cannot verify arithmetic the model did.                                                   |
| Owned thin tool-use loop behind an `AgentRunner` port                                 | Adopt ADK / LangGraph now                                         | The loop is where the gate lives; it is tiny; the port keeps frameworks adoptable later for multi-agent handoffs without touching tools, evidence or safety. |
| Deterministic detectors emit events; model only composes                              | Let the model scan data on a schedule and decide what matters     | Free, reproducible, testable; the expensive part runs only when something happened.                                                                          |
| Gate = side effect × quality × history, with money/regulator always human             | Model self-reported confidence; global on/off autonomy            | Autonomy is earned per watcher from real approvals and can be lost; the one unbreakable rule stays unbreakable.                                              |
| One Postgres for everything (events table, pgvector, snapshots)                       | Kafka, a dedicated vector DB, Redis-first                         | At this volume a second datastore is a second failure mode; each can be added when a named load demands it.                                                  |
| Raw kept forever; canonical rebuilt from raw                                          | Map in flight and discard raw                                     | Re-map without re-fetching; prove what the source said; sources have no reliable date filters.                                                               |
| Canonical envelope with `(company_id, source, source_ref)` and `type:code` references | Per-source schemas; surrogate keys only                           | Multiple sources for one company and one customer across a group become joins, not projects.                                                                 |
| BFF with internal key; API enforces tenancy                                           | Browser → API directly with Supabase RLS                          | No secrets in the browser; one place decides authorisation; RLS remains a possible second layer.                                                             |
| On-premises bridge for Tally with a durable local queue                               | Ask customers to expose port 9000; cloud-hosted Tally only        | Tally cannot call out and the PC is often offline; a buffered relay is the only design that survives real accounts rooms.                                    |
| Become the ERP by posting to the statutory ledger (Option A) before replacing it      | Build a full accounting package first                             | The CA and the audit already trust Tally; BIDE owns the work upstream and proves value; full replacement is a later product.                                 |
| Role seeds layout; permissions gate actions; one card catalogue                       | Separate dashboards per role                                      | Same tools, same numbers, different first screen; nothing forks.                                                                                             |
| Eval harness as the release gate                                                      | Manual QA; monitoring only                                        | An LLM feature has no compiler; the scoreboard is what makes "better" measurable and "worse" unshippable.                                                    |

## 12 · Risks

| Risk                                                                | Likelihood | Mitigation in the design                                                                             |
|---------------------------------------------------------------------|------------|------------------------------------------------------------------------------------------------------|
| Confident-wrong output destroys trust in one session                | Medium     | Numeric guard, confidence labels on cards, refusal as a designed mode, eval ship-gate                |
| Source API changes silently (TranzAct re-keyed reports in Aug 2026) | High       | Catalogue-resolved identifiers; raw kept; sync health alerts; mapper tests per source                |
| Tally site variability (versions, LAN, PC off)                      | High       | Bridge heartbeat and plain-language alerts; tolerant XML decoding; file-drop fallback                |
| Per-company customisation turns product into consulting             | Medium     | One codebase, differences as settings and workflow rows; days-per-onboarding tracked                 |
| Cost surprise from model calls                                      | Medium     | Detectors before model; capped payloads; tiers; budgets; cost per pass logged                        |
| Entity resolution errors merge the wrong customers                  | Medium     | Exact matches auto, fuzzy matches confirm; aliases carry confidence and confirmer; merges reversible |
| Outbound message sent twice or to the wrong contact                 | Low        | Idempotent actions; per-customer send caps; contact shown at approval; delivery receipts             |
| Single in-process scheduler stalls the API                          | Medium     | Split worker at the named trigger; jobs bounded by time and pages                                    |

Diagrams are schematic: box contents name responsibilities, arrows name the data or command that moves. Mechanism detail for each field, the Tally bridge, and the ERP migration is in the BIDE Build Reference; current status and gaps are in the BIDE Stage Review.
