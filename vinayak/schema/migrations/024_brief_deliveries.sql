-- ============================================================
-- Migration 024 — brief_deliveries: the brief, as evidence
-- ============================================================
-- The month-3 demo is judged on a sentence: "the morning brief has arrived in
-- his inbox every working day for the preceding 30 days". Until now the brief
-- only wrote a log line to stdout, which proves nothing a week later and can
-- not be counted at all. This table is the proof.
--
-- One row per ATTEMPT per recipient, including the failures. A day with a
-- failed attempt and no success is a missed day, and it is worth being able
-- to say why it was missed (provider down, no provider configured) rather
-- than just that it was.
--
-- What the brief said is kept as the subject and the card keys it was built
-- from — enough to answer "what did he see that morning" without storing the
-- whole email body a second time.
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/024_brief_deliveries.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS brief_deliveries (
    id            BIGSERIAL PRIMARY KEY,
    company_id    TEXT NOT NULL,
    recipient     TEXT NOT NULL,                 -- lower-cased email
    -- The IST calendar day the brief was FOR. Stored rather than derived from
    -- sent_at so a retry after midnight UTC still counts for the right day.
    sent_on       DATE NOT NULL,
    sent_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    delivered     BOOLEAN NOT NULL DEFAULT FALSE,
    provider      TEXT,                          -- resend | smtp | NULL (not configured)
    error         TEXT,
    subject       TEXT,
    card_keys     JSONB NOT NULL DEFAULT '[]'::jsonb,
    urgent        INTEGER NOT NULL DEFAULT 0
);

-- The readiness question: distinct delivered days per recipient in the last
-- N days. Partial on delivered so failed attempts never bloat the index the
-- evidence query walks.
CREATE INDEX IF NOT EXISTS idx_brief_deliveries_delivered_days
    ON brief_deliveries (company_id, recipient, sent_on DESC)
    WHERE delivered;

-- "What went out this morning, and what failed" across all workspaces.
CREATE INDEX IF NOT EXISTS idx_brief_deliveries_recent
    ON brief_deliveries (sent_on DESC, company_id);

COMMIT;
