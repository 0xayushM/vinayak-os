-- ============================================================
-- Migration 025 — worker health: a heartbeat, and alerts that say so once
-- ============================================================
-- The worker is the part of the system nobody looks at. When it stops, the
-- dashboard does not break — it just quietly stops changing — and the first
-- person to notice is the owner, days later, asking why the numbers are old.
-- Two tables turn that into something that gets noticed within minutes:
--
--   worker_heartbeats — one row per scheduler process (the worker service, or
--     the API when it runs with RUN_SCHEDULER=1). A job rewrites last_beat_at
--     every minute. "Is background work running?" becomes a timestamp
--     comparison instead of a guess. The check that reads it cannot live in
--     the worker (a dead worker does not report its own death); the API runs
--     it — see vinayak/health.py.
--
--   alerts — the memory that keeps an alert from becoming noise. One row per
--     CONDITION ("sync of sales_invoices for kbrushes is failing"), keyed by
--     dedupe_key, with when it was last seen and last emailed. A condition
--     that persists re-alerts after a cooldown, not every hour it recurs.
--
-- Why not the events bus (021): an event's dedupe key means "this fact
-- happens once, ever", and events are handed to the brain's consumers to act
-- on. An alert is the opposite on both counts — it must be allowed to fire
-- again after a cooldown, it is about the system rather than a company's
-- business, and nothing should ever propose an action because of one.
--
-- Idempotent + safe to re-run:
--   python -m vinayak.scripts.migrate
-- ============================================================

BEGIN;

-- ── Heartbeats ───────────────────────────────────────────────────────────
-- worker_id is stable across restarts of the same service (WORKER_ID, else
-- the Railway replica id, else hostname) so a restart updates its row rather
-- than adding one; started_at shows the restart. Rows for hosts that have
-- not beaten in a week are pruned by the beat itself.
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id     TEXT PRIMARY KEY,
    role          TEXT NOT NULL DEFAULT 'worker',   -- worker | api (RUN_SCHEDULER=1)
    hostname      TEXT,
    pid           INTEGER,
    version       TEXT,                             -- git sha when the platform provides one
    started_at    TIMESTAMPTZ NOT NULL,
    last_beat_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    jobs          INTEGER NOT NULL DEFAULT 0,       -- jobs registered on the scheduler
    beats         BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_worker_heartbeats_recent
    ON worker_heartbeats (last_beat_at DESC);

-- ── Alerts ───────────────────────────────────────────────────────────────
-- kind: sync_failed | canonical_failed | creds_failed | watcher_halted |
--       brief_failed | job_error | worker_stale
-- company_id is NULL for conditions that belong to no workspace (the worker
-- being down). The Sync page only ever shows a workspace its own alerts and
-- the global ones — never another company's.
CREATE TABLE IF NOT EXISTS alerts (
    dedupe_key     TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    company_id     TEXT,
    subject        TEXT NOT NULL,
    detail         TEXT,
    first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    times_seen     INTEGER NOT NULL DEFAULT 1,
    last_sent_at   TIMESTAMPTZ,          -- NULL = never successfully emailed
    times_sent     INTEGER NOT NULL DEFAULT 0,
    last_error     TEXT                  -- why the last email did not go out
);

CREATE INDEX IF NOT EXISTS idx_alerts_recent
    ON alerts (company_id, last_seen_at DESC);

COMMIT;
