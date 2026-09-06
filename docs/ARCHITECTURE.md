# BIDE — Architecture & Call-Flow Map

*How the system is put together after the restructure, and exactly what runs
when. Read §1–3 for the shape, §4 for the call-flows (file → class → function),
§5 for the two answer engines, §6 for where to change things safely.*

---

## 1. The one mental model

Every feature is one loop pointed at different data:

```
Trigger → Gather → Reason → Gate → Act → Remember
```

A chat question, a scheduled sync, and (later) an emitted event are three
triggers into the same loop. There is one place that enforces grounding, one that
enforces the confidence gate, one that writes memory — so new capabilities are new
triggers/tools/workflows, never new control flow.

---

## 2. Module map & dependency DAG (post-restructure)

Arrows point downward only — no module imports something above it.

```
config.py                      env → constants
  │
domain/            models.py (Evidence, Claim, Answer) · money.py (Money, num_tokens, norm_num)
  │
db/                session.py (Database, `db`)
  │
schema/queries.py  55 SQL read functions → typed dicts        (the repository)
  │
query/             service.py (QueryService, `service`)        ← the single read "door"
  │
memory/            store.py · entity_summary.py
tools/             contract.py (Tool, ToolResult) · registry.py · executor.py · read_tools.py · action_tools.py
model/             port.py (ModelPort) · anthropic.py (AnthropicModel, get_model)
  │
reasoning/         safety.py (grounded/confidence/safe_summary) · llm.py (Anthropic prompts)
reasoning/engine/  __init__.py (answer, handlers, gates) · router.py (INTENTS, classify)
  │
agents/            runner.py (AgentRunner, get_runner) · native.py · adk.py
  │
api/               deps.py (get_db, get_current_user, require_workspace) · main.py · routes/*
eval/              harness.py · cases.py
```

`reasoning/engine` re-exports the core types (`Evidence/Answer/inr/_num_tokens/...`) from `domain/` for callers that predate the split.

---

## 3. The frozen contracts and their homes

| Contract | Class / symbol | File |
|---|---|---|
| Value types | `Evidence`, `Claim`, `Answer` | `domain/models.py` |
| Money format / tokens | `Money`, `num_tokens`, `norm_num` | `domain/money.py` |
| DB gateway | `Database`, `db` | `db/session.py` |
| Reads (the door) | `QueryService`, `service` | `query/service.py` |
| Tools | `Tool`, `ToolResult`, registry, executor | `tools/` |
| Model | `ModelPort` → `AnthropicModel` | `model/` |
| Safety spine | `grounded` / `confidence` / `safe_summary` | `reasoning/safety.py` |
| Orchestration | `AgentRunner` → `NativeAgentRunner` / `AdkAgentRunner` | `agents/` |
| Sources | `TokenCacheRegistry`, adapters | `adapters/` |
| Canonical | `distinct_company_ids`, builders | `canonical/` |
| Tenancy | `require_workspace`, `get_current_user` | `api/deps.py` |

---

## 4. Call-flows (what runs when)

### 4.1 Chat / Ask — the main path  ·  `POST /dashboard/ask`

```
api/main.py                       mounts dashboard.router at /dashboard
└─ routes/dashboard.ask()
   ├─ Depends require_workspace() (api/deps → routes/workspaces)   → company_id  [tenancy]
   ├─ Depends get_current_user()  (api/deps → routes/auth)         → TokenPayload [JWT]
   ├─ _conn()  = api/deps.get_db()  → db.session.Database.connect()
   ├─ reasoning/history: _owns_thread / create_thread / list_turns → thread + briefs
   ├─ reasoning/agent.should_use()                                 → agent path?
   ├─ agents.get_runner()  (agents/runner._make_runner via AGENT_RUNNER)
   │    └─ NativeAgentRunner.run()  (agents/native.py)
   │         └─ reasoning/agent.run_agent():
   │              ├─ _as_model(client) → model.get_model() → AnthropicModel   [ModelPort]
   │              ├─ tools/read_tools.register_all() → tools/registry (18 read tools)
   │              ├─ registry.anthropic_schemas(read_only=True)
   │              ├─ LOOP: mdl.chat(system, messages, tools)
   │              │        → AnthropicModel.chat → llm._get_client().messages.create
   │              ├─ on tool_use: registry.get(name)
   │              │        → tools/executor.execute(ctx, tool, input)
   │              │        → tool.fn → query.service.QueryService.<fn>
   │              │        → schema/queries.<fn>(conn, company_id)  → SQL
   │              │        → ToolResult(data, evidence, quality)
   │              ├─ safety.grounded()  → numeric-guard retry → safety.safe_summary()
   │              └─ safety.confidence() → _finalize() → Answer.to_dict()
   │         (fallback if no model / model error) → engine.answer(use_llm=False)
   └─ reasoning/history.save_turn()
```

Confidence label and grounding are set by **`reasoning/safety.py`**, deterministically
— never by the model. Every ₹ figure in the answer must trace to a tool's
`Evidence` (rounded display *or* exact raw value), or it is corrected/blocked.

### 4.2 Dashboard panel  ·  `GET /dashboard/<panel>`
```
routes/dashboard.<panel>() → require_workspace → _conn (api/deps.get_db)
  → schema/queries.<fn>(conn, company_id) → _envelope(data, report_id)
  → JSON {data, meta:{stale, last_synced_at}}
```

### 4.3 Action (human-in-the-loop)  ·  `POST /dashboard/actions/*`
```
actions_draft_chase() → registry.get("collections.draft_chase")
   → executor.execute() → action_tools.compose_chase() → INSERT actions (status=proposed)
actions_list()   → SELECT actions WHERE status=proposed             [the approval inbox]
actions_decide() → UPDATE actions SET status=approved|rejected      [the human gate]
```
Money/regulator actions are proposed only — never executed without a person.

### 4.4 Ingestion / sync  ·  `pipelines/scheduler.py` (APScheduler, hourly)
```
scheduler → Pipeline.run_chunk()
  ├─ adapter auth  (adapters/{tranzact,zoho}/auth.py: TokenCacheRegistry.get_or_create)
  ├─ adapter client.fetch_report()            (pagination, throttle, backoff)
  ├─ RowSchema validate (Pydantic; remap_api_fields, coerce_date → helpers.epoch_to_date)
  ├─ _upsert raw tables (content hash → helpers.stable_row_id)
  ├─ canonical rebuild (canonical/*: distinct_company_ids → _rebuild_*)
  └─ memory/entity_summary refresh
```

### 4.5 Auth / tenancy  ·  every request
```
/auth/login → bcrypt verify → JWT → httpOnly cookie
get_current_user() → decode JWT → TokenPayload
require_workspace() → X-Workspace-Id or JWT company_id → authorise → company_id
                      (scopes every query; injected by the layer, never model-chosen)
```

### 4.6 Eval / ship-gate  ·  `python -m vinayak.eval.harness [company] [--runner native|adk]`
```
run_eval() → per case: _answer_for()
   ├─ default → engine.answer(use_llm=False)          (deterministic, fast, free)
   └─ --runner → agents.make_runner(name).run()       (grades a live orchestrator)
   → _grade() → compute_metrics(): citation_compliance (must=1.0), correct_refusal_rate,
     bucket_accuracy, must_not_say_violations → ship_blocked
```

---

## 5. The two answer engines + the safety spine

**Native agent** (`reasoning/agent.run_agent`, default): the model calls read tools,
gathers `Evidence`, and writes prose; `reasoning/safety.py` then enforces grounding
(one self-correcting retry, then an evidence-only fallback) and assigns the
confidence label. Reaches the model only through `ModelPort`.

**Deterministic engine** (`reasoning/engine.answer`, fallback / no-key): `router.classify()`
picks an intent; `HANDLERS[intent]` (a `_h_*` function) calls `QueryService`, builds
`Answer` with `Claim`s each citing an `Evidence` id; `_validate()` downgrades any
uncited computed claim; `_gates()` sets the floor; optional `llm.phrase()` rewrites
prose under the same numeric guard (`_numbers_supported`).

**The spine is shared.** Both paths ground every ₹ figure on `Evidence` and label
confidence deterministically — that guarantee is identical regardless of which
engine (or, later, which orchestrator adapter) ran.

---

## 6. Where to change things without breakage

| To change… | Touch only… | Everything else is unaffected because… |
|---|---|---|
| Model provider | `model/anthropic.py` (or a new `ModelPort` impl) | callers depend on `ModelPort`, not the SDK |
| Orchestrator (native → ADK/LangGraph) | add an `AgentRunner` in `agents/`; set `AGENT_RUNNER` | `/ask` calls `get_runner()`; safety/tools unchanged |
| Add a data source | new adapter under `adapters/` + mapper under `canonical/` | they conform to the adapter/canonical contracts |
| Add a read | a function in the repository, exposed via `QueryService` | tools/engine read through the one door |
| Add a tool | declare against `tools/contract.Tool` | registry/executor/gate reason about it uniformly |
| Add a vertical | tools + workflow config + eval cases | no new loop, gate, or memory rule (see finalized architecture) |

---

## 7. Current state (honest)

**Restructured & green (Stages 0–6):** `domain/`, `db/`, `model/`, `query/`, `agents/`,
`reasoning/engine/` (package + router extracted), `api/deps.py`; real duplication
removed (money formatting, `_conn`, token-cache boilerplate, `_companies`). 155
unit tests pass; the eval ship-gate is 29/29 at 100% citation compliance.

**Deliberately deferred (need test scaffolding first, then safe to do):**
- Atomizing the engine `_h_*` handlers + `answer()` into `engine/handlers.py` +
  `engine/pipeline.py` (high coupling; fallback path).
- Splitting `dashboard.py`'s 58 endpoints into `routes/{finance,ar,…}.py` (needs
  TestClient smoke tests to verify).
- Making ADK the primary runner (`AGENT_RUNNER=adk`) — gated on completing the ADK
  session loop and passing `--runner adk` on the harness with a live `google-adk`.
```
