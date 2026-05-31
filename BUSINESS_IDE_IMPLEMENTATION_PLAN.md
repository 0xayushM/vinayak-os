# Business IDE — Implementation Plan

How to get from what we have (a Tranzact dashboard) to what we want (a reusable
engine + per-company context, with a parser, a learning memory, and an AI that
knows when to stay quiet). Written to be built in order. Each phase ships something
usable and de-risks the next.

---

## Where we are today (the honest starting point)

- **Layer 1 (storage + aggregation): mostly built.** `tz_*` tables hold Tranzact
  data scoped by `company_id`; `queries.py` has ~20 pre-aggregated query functions;
  the dashboard reads them.
- **Layer 0 (parser): not built.** Our `tz_` tables are *Tranzact-shaped*, not
  canonical. There is no source-independent representation of an invoice yet. Today
  "add Tally" would mean rewriting queries.
- **Layer 2 (memory): not built.** Nothing captures what the owner tells us.
- **Layer 3 (reasoning): the dashboard exists, the AI does not.** No chat, no
  calibrated-confidence reasoning, no eval.

So: the surface is real, the substance is not. This plan builds the substance.

---

## The four things to build (and the order)

1. **Canonical schema + adapter pattern** — turn Tranzact into the *first adapter*,
   not the data model itself.
2. **Memory layer** — durable, decaying, queryable facts captured from the owner.
3. **Calibrated reasoning + eval harness** — the AI answers, tags every claim, and
   we *measure* whether it lies. This is our substitute for Cursor's compiler.
4. **Second adapter (Tally or Busy)** — the only real proof the engine generalizes.

Light actions (draft-and-approve) come after all four. They're a feature, not the moat.

---

## Phase 1 — Canonical schema + Tranzact as an adapter

**Goal:** the dashboard reads from a *source-independent* model. Adding a new ERP
later means writing one adapter, touching zero query functions.

### 1a. Define the canonical objects (first cut)

Start only with what manufacturing AND trading both have and what we already pull:

```
canon_party            (customers + vendors; role flag. unifies "who")
canon_item             (SKU / product)
canon_sales_invoice    + canon_sales_invoice_line
canon_purchase_invoice + canon_purchase_invoice_line
canon_order            (sales or purchase; type flag)
canon_payment          (receipts + payments; AR/AP)
canon_stock            (inventory snapshot)
canon_production        (manufacturing only — can be empty for traders)
```

Every canonical row carries the same envelope:

```
id            uuid
company_id    text          -- tenant scope (already our pattern)
source        text          -- 'tranzact' | 'tally' | 'busy' | 'excel'
source_ref    text          -- the original row/voucher id, for traceability
ingested_at   timestamptz
confidence    real           -- how sure the adapter is about this mapping (0..1)
raw           jsonb          -- the untouched source row, always kept
... typed canonical fields ...
```

Two rules that matter:
- **Always keep `raw`.** When a mapping is wrong later, we can re-map without re-fetching.
- **Log, don't guess.** Anything the adapter can't confidently map goes to
  `ingest_issues (company_id, source, source_ref, field, reason)` instead of being
  filled with a plausible-but-wrong value. This table *is* our backlog of parser work.

### 1b. The adapter contract

One Python interface every source implements:

```
class SourceAdapter:
    def extract(self, company_id, window) -> list[RawRow]: ...
    def map(self, raw: RawRow) -> CanonResult: ...   # -> canonical row OR Unmapped
    def load(self, canon_rows) -> None: ...          # upsert into canon_*
```

Our existing Tranzact pipelines become the first `SourceAdapter`. The `extract`
step is what they already do; we add `map` (tz row -> canon) and write to `canon_*`.

### 1c. Repoint queries

Rewrite `queries.py` to read `canon_*` instead of `tz_*`. The function signatures
and the API stay identical, so the dashboard doesn't change. This is the moment the
product stops being "a Tranzact tool" and becomes "an engine that currently has one
adapter."

**Done when:** the dashboard looks identical but is fed by `canon_*`, and a Tranzact
row's journey (raw → canon → query → panel) is fully traceable.

---

## Phase 2 — The memory layer (the actual moat)

**Goal:** capture what the owner knows, the moment they reveal it, and never ask
again — *until the fact goes stale*. The decay handling is what makes this safe.

### 2a. The fact store

```
memory_fact
  id            uuid
  company_id    text
  entity_type   text      -- 'party' | 'item' | 'company' | ...
  entity_ref    text      -- e.g. 'party:dev-colour'
  claim_key     text      -- e.g. 'payment_terms_days'
  claim_value   jsonb     -- 60
  origin        text      -- 'user_confirmed' | 'ai_inferred' | 'imported'
  confidence    real      -- 1.0 for user-confirmed, lower for inferred
  created_at    timestamptz
  source_msg_id uuid      -- the chat turn it came from (provenance)
  valid_until   timestamptz null  -- when to re-check (null = no expiry)
  last_validated_at timestamptz
  status        text      -- 'active' | 'stale' | 'superseded'
  superseded_by uuid null
```

The DB is the source of truth. The `customers/dev-colour.md` files from the doc are
a **rendered view** of the active facts for an entity — nice for humans and for
loading into the AI's context, but never the place we write to.

### 2b. The capture loop

When the AI states something and the owner corrects or confirms it, we write a fact.
Concretely: the AI's answer carries structured claims (see Phase 3); a "✓ correct /
✗ that's wrong because…" affordance on each claim writes a `memory_fact` with
`origin = user_confirmed, confidence = 1.0`.

### 2c. Decay — the part the ideation doc missed

A fact is not true forever. Two ways it goes stale:

- **Time-based:** facts with a `valid_until` (e.g. "on a 3-month trial price") expire.
- **Data-contradiction:** a nightly job checks active facts against live canonical
  data. If a fact says "DEV COLOUR pays in 60 days" but their last 5 invoices cleared
  in 95, mark the fact `stale` and queue a re-ask.

**Re-validation flow:** before the AI *relies* on a stale or soon-to-expire fact, it
doesn't silently use it — it asks: "Last you told me DEV COLOUR is on 60-day terms.
Their recent invoices are clearing in ~95. Still 60, or has it changed?" The answer
refreshes or supersedes the fact. This is what stops our own memory from becoming the
confident-wrong failure we're afraid of.

**Done when:** correcting the AI once changes its answer next time, AND a fact that
contradicts the data gets flagged and re-asked instead of repeated.

---

## Phase 3 — Calibrated reasoning + the eval harness

**Goal:** the AI answers questions, and every statement is provably one of: a computed
fact, a flagged inference, or an honest "I can't know that." And we can *measure* how
often it gets that classification wrong — before a customer does.

### 3a. Architecture that makes "say no" structural, not just a prompt

Prompting alone ("please be careful") is not enough. We separate the steps so the AI
*physically cannot* state a number it wasn't given:

1. **Retrieve (deterministic):** answer the question by calling our `queries.py`
   functions. These return real numbers + the memory facts relevant to the entity.
2. **Reason (the AI):** the model receives only (a) those computed numbers, each with
   an id, (b) the memory facts with their confidence, (c) the static company profile.
3. **Structured output:** the AI must return claims in a schema, each tagged:
   - `computed` — must cite the id of a number it was given.
   - `inference` — must state the assumption ("assuming these are arm's-length sales").
   - `unknown` — becomes a question, routed to the memory capture loop.
4. **Validate (deterministic, post-check):** before display, we verify every
   `computed` claim traces to a real provided number. If it doesn't, we block or
   downgrade it. A fabricated "fact" never reaches the owner.

The UI renders the three classes differently (plain / flagged / a question). The
KBrushes tags were the prototype of this.

### 3b. The eval harness — our synthetic compiler

The doc says business advice has no compiler. We build an approximate one: a golden
test set that runs on every prompt or model change.

```
eval_case
  question        -- "Which customers are a concentration risk?"
  data_snapshot   -- frozen canonical data so results are deterministic
  gold_answer     -- what a good answer contains
  gold_buckets    -- which claims should be computed / inference / unknown
  must_not_say    -- claims that would be hallucinations or overconfidence
```

Metrics we track release-over-release:
- **Bucket accuracy** — did it classify computed vs inference vs unknown correctly?
  (The lethal error is calling an inference a fact — weight that heavily.)
- **Unsupported-claim rate** — % of `computed` claims that don't trace to a number.
- **Correct-refusal rate** — when the answer wasn't in the data, did it ask instead
  of guessing?

Seed the golden set from the Agarwal companies (real questions, real data), grow it
every time the AI gets something wrong in practice. **No prompt/model change ships if
unsupported-claim rate rises.** This discipline is the product.

**Done when:** we have a number, tracked over time, for "how often does the AI state
something it can't support," and it's going down.

---

## Phase 4 — Second adapter (the real generalization test)

**Goal:** prove the engine is reusable by onboarding a *different* source into the
*same* canonical schema, touching zero query/AI code.

Pick **one** based on the group's needs — Busy is likely lower-pain than Tally and
the group needs it anyway. Build it as a `SourceAdapter` (Phase 1b). The test of
success is brutal and clear: **how much of the query layer, the memory layer, and
the AI did we have to change? If the answer is "almost nothing," the moat is real.
If we had to fork everything, "one engine, many sources" was a story.**

This phase also answers Open Question #1 from the ideation doc (how much of the
parser the AI can do vs. hand-built): try letting the model propose the raw→canon
mapping for a messy source and measure how often a human has to fix it.

---

## Phase 5 — Light actions (last, and gated)

Only after the above. Every action is **draft → human approves → execute**, never
autonomous on anything irreversible. Start with the safest, highest-frequency one
the owners actually want (likely AR follow-ups), and keep the same calibrated tags:
the AI drafts, shows its reasoning, the human sends.

---

## What to pick before writing code

These are decisions, not tasks — answer them first:

1. **One vertical, for real.** Manufacturing *or* trading, not both. Pick the Agarwal
   company with the cleanest data and a decision its owner makes monthly.
2. **First-cut canonical objects.** Confirm the 9 above are right for that one vertical;
   cut any that don't apply (a trader has no `canon_production`).
3. **Second source for Phase 4.** Busy vs Tally — decide now, because it shapes how
   abstract the canonical schema needs to be.
4. **The first eval questions.** Write 10 real questions the chosen owner would ask.
   These become the first golden cases and they anchor the whole reasoning design.

---

## The one-line version

Phase 1 makes us an engine instead of a Tranzact tool. Phase 2 builds the moat
(memory that learns *and forgets correctly*). Phase 3 makes the AI trustworthy *and
measurably so*. Phase 4 proves it generalizes. Everything else is surface — important
for selling, but not what makes this defensible.
