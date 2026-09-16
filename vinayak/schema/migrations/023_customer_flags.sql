-- ============================================================
-- Migration 023 — customer_flags: the first synapse
-- ============================================================
-- The architecture's claim is that the fields talk to each other. This is the
-- first place it is actually true: Accounts notices that a customer is a
-- credit risk, and Sales sees it on the quote screen before the next order is
-- taken. Without the table in between, the two halves of the business each
-- know something the other needs and neither finds out.
--
-- A flag is a FACT with a life, not a computed value. It is raised with a
-- reason and the evidence behind it, it can be overridden by a person who
-- knows something the data does not, and it is cleared when the cause goes
-- away. That history is the point: "why was this customer on hold in March"
-- is a question somebody will ask.
--
-- Idempotent + safe to re-run.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS customer_flags (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    TEXT NOT NULL,
    customer_ref  TEXT NOT NULL,
    -- 'hold'  — do not extend more credit without a decision
    -- 'watch' — take the next order, but know what you are taking
    level         TEXT NOT NULL,
    reason        TEXT NOT NULL,             -- one sentence, in the owner's language
    evidence      JSONB NOT NULL DEFAULT '{}'::jsonb,
    source        TEXT NOT NULL DEFAULT 'agent',   -- agent | user
    raised_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    cleared_at    TIMESTAMPTZ,
    cleared_by    TEXT,
    clear_reason  TEXT,
    -- A person can override the machine: "I know, they are good for it, the
    -- MD has agreed terms." An override is honoured until it is revoked, and
    -- the detector must not keep re-raising over the top of it.
    overridden    BOOLEAN NOT NULL DEFAULT FALSE,
    overridden_by TEXT
);

-- One live flag per customer. Raising a second is an UPDATE of the first.
CREATE UNIQUE INDEX IF NOT EXISTS ux_customer_flags_live
    ON customer_flags (company_id, customer_ref)
    WHERE cleared_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_customer_flags_history
    ON customer_flags (company_id, customer_ref, raised_at DESC);

COMMIT;
