-- ============================================================
-- Migration 019 — tz_sync_runs.company_id: drop the legacy default
-- ============================================================
-- Databases created before the multi-workspace refactor carried
--   company_id TEXT NOT NULL DEFAULT 'kbrushes'
-- on tz_sync_runs, and BasePipeline._start_run never wrote company_id —
-- so every TranzAct sync run was silently tagged 'kbrushes' regardless of
-- the workspace that actually synced. Sync health, panel freshness and the
-- stale badges (all filtered by company_id) were therefore reading the
-- wrong rows for every other workspace.
--
-- The code now writes company_id explicitly (pipelines/base.py). This
-- migration removes the default so a missing company_id fails loudly
-- instead of mis-attributing again.
--
-- Re-attribution of historical rows is intentionally NOT attempted: the
-- old rows carry no other tenant marker, so we cannot tell which workspace
-- they belonged to. They age out of the freshness window (SYNC_STALENESS_HOURS)
-- after the first correctly-tagged run per pipeline.
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/019_sync_runs_company_id.sql
-- ============================================================

BEGIN;

ALTER TABLE tz_sync_runs ALTER COLUMN company_id DROP DEFAULT;
ALTER TABLE tz_sync_runs ALTER COLUMN company_id SET NOT NULL;

COMMIT;
