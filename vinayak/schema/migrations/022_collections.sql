-- ============================================================
-- Migration 022 — collections: the ladder, the promise, the dispute
-- ============================================================
-- Sprint 2 could draft a reminder. It could not remember that it had, which
-- is the difference between chasing and nagging. Three tables of memory:
--
--   collections_state — one row per customer. Which rung of the ladder they
--     are on, when they were last chased, whether chasing is paused, and
--     whether the balance is disputed. Everything the next chase needs to
--     know before it is written.
--
--   promises — "we'll pay on the 20th", recorded as a fact with a date.
--     A promise pauses chasing until it is due, and breaking one is an event
--     worth acting on. This is the single most useful thing a collections
--     process can record and the thing least often written down.
--
--   chase_log — when a reminder actually went out, per customer and rung.
--     The actions ledger holds the proposal; this holds the delivery, which
--     is what recovery has to be measured from.
--
-- Idempotent + safe to re-run.
-- ============================================================

BEGIN;

-- ── Per-customer collections state ───────────────────────────────────────
-- rung: 0 = never chased, then 1-4 up the ladder. The ladder only ever goes
-- up while a balance stays unpaid; it resets when the customer clears.
CREATE TABLE IF NOT EXISTS collections_state (
    company_id      TEXT NOT NULL,
    customer_ref    TEXT NOT NULL,
    rung            INTEGER NOT NULL DEFAULT 0,
    last_chased_at  TIMESTAMPTZ,
    last_rung_at    TIMESTAMPTZ,
    chases_sent     INTEGER NOT NULL DEFAULT 0,
    -- Chasing is paused while a promise is open, or by hand for a reason.
    paused_until    DATE,
    pause_reason    TEXT,
    -- A disputed balance must never be chased automatically: the argument is
    -- about the invoice, and a reminder makes it worse.
    disputed        BOOLEAN NOT NULL DEFAULT FALSE,
    dispute_note    TEXT,
    disputed_at     TIMESTAMPTZ,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, customer_ref)
);

-- ── Promises to pay ──────────────────────────────────────────────────────
-- status: open -> kept | broken | cancelled
CREATE TABLE IF NOT EXISTS promises (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id    TEXT NOT NULL,
    customer_ref  TEXT NOT NULL,
    amount        NUMERIC,                -- NULL = "the balance"
    promised_on   DATE NOT NULL,          -- the day they said they would pay
    made_on       DATE NOT NULL DEFAULT CURRENT_DATE,
    recorded_by   TEXT,
    note          TEXT,
    status        TEXT NOT NULL DEFAULT 'open',
    settled_at    TIMESTAMPTZ,
    -- What the customer owed when the promise was made, so "kept" can be
    -- judged against the balance at the time rather than today's.
    balance_at_promise NUMERIC,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_promises_open
    ON promises (company_id, status, promised_on);
CREATE INDEX IF NOT EXISTS idx_promises_customer
    ON promises (company_id, customer_ref, created_at DESC);

-- ── What actually went out ───────────────────────────────────────────────
-- The actions ledger records the PROPOSAL. Recovery has to be measured from
-- the moment a reminder was DELIVERED, which is a different event and
-- sometimes never happens (no email on file, provider down).
CREATE TABLE IF NOT EXISTS chase_log (
    id            BIGSERIAL PRIMARY KEY,
    company_id    TEXT NOT NULL,
    customer_ref  TEXT NOT NULL,
    rung          INTEGER NOT NULL,
    action_id     UUID,
    channel       TEXT NOT NULL DEFAULT 'email',
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- The balance at the moment of sending. Recovery is this minus what they
    -- owe later, which is only meaningful if we captured the "before".
    balance_at_send NUMERIC,
    approved_by   TEXT
);

CREATE INDEX IF NOT EXISTS idx_chase_log_customer
    ON chase_log (company_id, customer_ref, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_chase_log_recent
    ON chase_log (company_id, sent_at DESC);

COMMIT;
