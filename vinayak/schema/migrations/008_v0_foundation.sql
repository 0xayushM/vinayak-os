-- 008_v0_foundation.sql
-- ──────────────────────
-- The three tables everything in v0 depends on (see docs/V0_FINANCE_SPEC.md §1):
--
--   ar_daily_snapshot — daily copy of the AR book. tz_ar_aging is upserted in
--     place and therefore has no memory; this table is the memory. It powers
--     aging drift, inferred payment dates (an invoice that disappears between
--     snapshots was paid), true days-to-pay, DSO trend, and the collections
--     before/after proof. One batch insert per company per day, rows are tiny,
--     retained forever. START THIS EARLY — every insight sharpens with history.
--
--   events — the synapse bus, minimal version. Workflows publish
--     ('invoice.overdue', 'promise.broken', …); workers poll for unprocessed
--     rows. Postgres-backed by design (no new infra) until volume demands more.
--
--   actions — the action ledger (Layer 9 seed). Every action the brain proposes
--     lives here through its whole life: proposed → approved/rejected →
--     executed/failed. The approval inbox is a view over this table. Idempotency
--     (never chase the same customer twice at the same rung) is enforced here.
--
-- Idempotent: safe to run more than once.

CREATE TABLE IF NOT EXISTS ar_daily_snapshot (
    company_id    TEXT NOT NULL,
    snap_date     DATE NOT NULL,
    invoice_ref   TEXT NOT NULL,          -- stable_row_id(invoice_number, customer_name)
    customer_name TEXT,
    invoice_number TEXT,
    invoice_date  DATE,
    due_date      DATE,
    outstanding   NUMERIC,
    days_overdue  INT,
    bucket        TEXT,                    -- 0-30 / 31-60 / 61-90 / 90+
    PRIMARY KEY (company_id, snap_date, invoice_ref)
);

CREATE INDEX IF NOT EXISTS idx_ar_snap_customer
    ON ar_daily_snapshot (company_id, customer_name, snap_date);

CREATE TABLE IF NOT EXISTS events (
    id           BIGSERIAL PRIMARY KEY,
    company_id   TEXT NOT NULL,
    event_type   TEXT NOT NULL,            -- 'invoice.overdue', 'credit.flagged', ...
    entity_ref   TEXT,                     -- 'customer:DEV COLOUR' / invoice_ref
    payload      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ               -- NULL = pending
);

CREATE INDEX IF NOT EXISTS idx_events_pending
    ON events (company_id, event_type, processed_at);

CREATE TABLE IF NOT EXISTS actions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   TEXT NOT NULL,
    tool_name    TEXT NOT NULL,            -- 'ar.draft_collection_email'
    entity_ref   TEXT,                     -- customer/invoice acted on
    payload      JSONB,                    -- the full proposal (draft email, PO, …)
    status       TEXT NOT NULL DEFAULT 'proposed',
                                           -- proposed | approved | rejected | executed | failed
    gate         TEXT NOT NULL,            -- auto | confirm | human
    proposed_by  TEXT,                     -- 'agent' or a user email
    decided_by   TEXT,
    decided_at   TIMESTAMPTZ,
    executed_at  TIMESTAMPTZ,
    result       JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_actions_inbox
    ON actions (company_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_actions_entity
    ON actions (company_id, tool_name, entity_ref, created_at DESC);
