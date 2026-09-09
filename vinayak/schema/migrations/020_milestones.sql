-- ============================================================
-- Migration 020 — Milestone evidence: usage, experiments, roles, incidents
-- ============================================================
-- Milestone 1 is judged on things the product must be able to PROVE:
--   • who used it on which days (60-consecutive-day, 4-days-a-week rule)
--   • which experiments were run and what came of them
--   • who is allowed to approve which actions (roles and permissions)
--   • whether there was a critical incident in the window
-- Nothing here changes how business data is read; it only records evidence.
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/020_milestones.sql
-- ============================================================

BEGIN;

-- ── Usage: one row per (company, user, day) on any authenticated request ──
CREATE TABLE IF NOT EXISTS usage_events (
    company_id   TEXT NOT NULL,
    user_email   TEXT NOT NULL,
    day          DATE NOT NULL,
    first_seen   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    requests     INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (company_id, user_email, day)
);
CREATE INDEX IF NOT EXISTS idx_usage_events_user_day ON usage_events (user_email, day DESC);

-- ── Experiments log ──────────────────────────────────────────────────────
-- source: 'ai_suggested' (a Strategy watcher proposed it) | 'manual'
-- status: 'proposed' → 'accepted' → 'running' → 'closed' (or 'rejected')
-- outcome: 'positive' | 'negative' | 'inconclusive' (set when closed)
CREATE TABLE IF NOT EXISTS experiments (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id     TEXT NOT NULL,
    title          TEXT NOT NULL,
    hypothesis     TEXT,
    source         TEXT NOT NULL DEFAULT 'manual',
    status         TEXT NOT NULL DEFAULT 'proposed',
    metric         TEXT,                       -- what we measure, in words
    baseline       NUMERIC,                    -- value before
    target         NUMERIC,                    -- value hoped for
    result         NUMERIC,                    -- value after
    outcome        TEXT,                       -- positive | negative | inconclusive
    outcome_notes  TEXT,
    action_refs    JSONB NOT NULL DEFAULT '[]'::jsonb,   -- action ids / entity refs involved
    evidence       JSONB NOT NULL DEFAULT '{}'::jsonb,   -- figures the suggestion was built from
    proposed_by    TEXT,                       -- 'agent' or a user email
    decided_by     TEXT,
    started_at     DATE,
    ends_at        DATE,
    closed_at      TIMESTAMPTZ,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_experiments_company_status ON experiments (company_id, status, created_at DESC);

-- ── Roles and approval permissions ──────────────────────────────────────
-- role: owner | finance | accountant | sales | viewer | admin (legacy default)
-- 'admin' is the pre-existing default and is treated as "role not chosen yet"
-- by the UI, which asks once.
ALTER TABLE users ADD COLUMN IF NOT EXISTS may_approve_messages BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS may_approve_money    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS pinned_cards         JSONB;
ALTER TABLE users ADD COLUMN IF NOT EXISTS display_name         TEXT;
-- Existing accounts were all admins who could approve: keep that true so
-- nothing that works today stops working after this migration.
UPDATE users SET may_approve_messages = TRUE, may_approve_money = TRUE
 WHERE role = 'admin' AND may_approve_messages = FALSE AND may_approve_money = FALSE;

-- ── Incidents ────────────────────────────────────────────────────────────
-- severity: 'critical' | 'major' | 'minor'. "Critical" is defined in
-- docs/INCIDENTS.md; the Milestone board counts critical rows only.
CREATE TABLE IF NOT EXISTS incidents (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id   TEXT,                          -- NULL = platform-wide
    severity     TEXT NOT NULL,
    title        TEXT NOT NULL,
    detail       TEXT,
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ,
    reported_by  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ── Platform settings (the milestone start date lives here) ─────────────
CREATE TABLE IF NOT EXISTS platform_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
INSERT INTO platform_settings (key, value) VALUES ('milestone_start_date', '2026-09-01')
ON CONFLICT (key) DO NOTHING;
INSERT INTO platform_settings (key, value) VALUES ('milestone_user_email', '')
ON CONFLICT (key) DO NOTHING;

-- ── Eval runs (the harness records here when asked to) ──────────────────
CREATE TABLE IF NOT EXISTS eval_runs (
    id                   BIGSERIAL PRIMARY KEY,
    ran_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    runner               TEXT NOT NULL DEFAULT 'engine',   -- engine | native | adk
    company_id           TEXT,
    cases_run            INTEGER NOT NULL,
    passed               INTEGER NOT NULL,
    citation_compliance  NUMERIC NOT NULL,
    factual_accuracy     NUMERIC,                          -- NULL until expected values exist
    ship_blocked         BOOLEAN NOT NULL,
    metrics              JSONB NOT NULL
);

COMMIT;
