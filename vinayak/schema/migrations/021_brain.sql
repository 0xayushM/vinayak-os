-- ============================================================
-- Migration 021 — the brain's own runtime: workflows, runs, deduped events
-- ============================================================
-- Sprint 1 gave the brain something to say (the Pulse). This gives it a
-- body: a registry of watchers, an episodic log of every time one ran, and
-- an event bus that cannot say the same thing twice.
--
--   workflows   — the declarative registry. One row per (company, watcher).
--                 Code declares what a watcher IS; this row decides whether
--                 it runs here, how often, and with what thresholds. Turning
--                 a watcher off is an UPDATE, never a deploy.
--
--   brain_runs  — the episodic log (Layer 8, "Remember"). Every watcher pass
--                 opens a run and closes it with what it found and proposed.
--                 This is the answer to "what has the brain been doing?" and
--                 the only honest way to debug a background system.
--
--   events      — gains a dedupe key. A detector is deterministic and runs
--                 hourly, so it re-derives the same facts every pass. The
--                 unique index is what makes "invoice X crossed 60 days" a
--                 single event rather than one an hour until it is paid.
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/021_brain.sql
-- ============================================================

BEGIN;

-- ── The event bus grows a memory ─────────────────────────────────────────
-- dedupe_key is the identity of the FACT, not of the row: 'INV-4471:rung60'
-- means "this invoice crossed the 60-day rung", and it can only happen once.
ALTER TABLE events ADD COLUMN IF NOT EXISTS dedupe_key   TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS severity     INTEGER NOT NULL DEFAULT 0;
ALTER TABLE events ADD COLUMN IF NOT EXISTS source       TEXT;      -- workflow key that emitted it
ALTER TABLE events ADD COLUMN IF NOT EXISTS run_id       BIGINT;    -- brain_runs.id
ALTER TABLE events ADD COLUMN IF NOT EXISTS processed_by TEXT;
ALTER TABLE events ADD COLUMN IF NOT EXISTS outcome      JSONB;     -- what the consumer did

CREATE UNIQUE INDEX IF NOT EXISTS ux_events_dedupe
    ON events (company_id, event_type, dedupe_key)
    WHERE dedupe_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_events_recent
    ON events (company_id, created_at DESC);

-- ── The watcher registry ─────────────────────────────────────────────────
-- interval_minutes, not cron: a watcher says how stale it tolerates being,
-- and the worker runs whatever is due. Nothing has to line up with a clock.
CREATE TABLE IF NOT EXISTS workflows (
    company_id       TEXT NOT NULL,
    workflow_key     TEXT NOT NULL,      -- 'detect.overdue_rung', 'strategy.weekly', ...
    enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    interval_minutes INTEGER NOT NULL DEFAULT 60,
    config           JSONB NOT NULL DEFAULT '{}'::jsonb,   -- per-company thresholds
    last_run_at      TIMESTAMPTZ,
    last_status      TEXT,               -- ok | error | skipped
    last_error       TEXT,
    consecutive_errors INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, workflow_key)
);

-- ── The episodic log ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS brain_runs (
    id               BIGSERIAL PRIMARY KEY,
    company_id       TEXT NOT NULL,
    workflow_key     TEXT NOT NULL,
    trigger          TEXT NOT NULL DEFAULT 'schedule',   -- schedule | manual | event
    started_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at      TIMESTAMPTZ,
    duration_ms      INTEGER,
    status           TEXT NOT NULL DEFAULT 'running',    -- running | ok | error
    events_emitted   INTEGER NOT NULL DEFAULT 0,
    actions_proposed INTEGER NOT NULL DEFAULT 0,
    summary          TEXT,               -- one sentence, built from the counts
    detail           JSONB NOT NULL DEFAULT '{}'::jsonb,
    error            TEXT
);

CREATE INDEX IF NOT EXISTS idx_brain_runs_recent
    ON brain_runs (company_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_brain_runs_workflow
    ON brain_runs (company_id, workflow_key, started_at DESC);

-- ── Experiments: a window, and a link back to the action that ran it ─────
-- "Run as experiment" on an Inbox approval writes both sides of this link,
-- so an ordinary chase becomes a logged experiment with an outcome for free.
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS window_days   INTEGER;
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS metric_key    TEXT;   -- machine-readable metric
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS auto_close    BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS entity_ref    TEXT;   -- customer:X / sku:Y
ALTER TABLE experiments ADD COLUMN IF NOT EXISTS dedupe_key    TEXT;   -- suppresses repeat suggestions

CREATE UNIQUE INDEX IF NOT EXISTS ux_experiments_dedupe
    ON experiments (company_id, dedupe_key)
    WHERE dedupe_key IS NOT NULL AND status IN ('proposed', 'accepted', 'running');

CREATE INDEX IF NOT EXISTS idx_experiments_due
    ON experiments (status, ends_at)
    WHERE status = 'running';

ALTER TABLE actions ADD COLUMN IF NOT EXISTS experiment_id UUID;
ALTER TABLE actions ADD COLUMN IF NOT EXISTS event_id      BIGINT;

COMMIT;
