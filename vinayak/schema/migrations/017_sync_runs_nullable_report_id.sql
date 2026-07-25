-- ============================================================
-- Migration 017 — tz_sync_runs.report_id nullable (multi-source)
-- ============================================================
-- tz_sync_runs now logs runs for BOTH TranzAct (numeric report IDs, e.g. 29)
-- and Zoho Books pipelines (named REST resources like "contacts"/"invoices",
-- which have no numeric report id). The NOT NULL integer constraint made every
-- Zoho sync fail at _start_run. Relax it so non-TranzAct sources log NULL.
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/017_sync_runs_nullable_report_id.sql
-- ============================================================

BEGIN;

ALTER TABLE tz_sync_runs ALTER COLUMN report_id DROP NOT NULL;

COMMIT;
