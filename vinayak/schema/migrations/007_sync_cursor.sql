-- 007_sync_cursor.sql
-- ─────────────────────
-- Resumable pagination cursor for TranzAct report syncs.
--
-- TranzAct's /generate_report exposes no usable server-side date filter, so a
-- brand's full history is migrated by walking pages (50 rows/page). This table
-- persists how far each report has been paged for each company, so a sync
-- resumes the REMAINING pages instead of re-fetching the whole report — and so
-- a long migration survives a process restart.
--
-- Idempotent: safe to run more than once.

CREATE TABLE IF NOT EXISTS tz_sync_cursor (
    company_id      TEXT NOT NULL,
    pipeline_name   TEXT NOT NULL,
    next_page       INT  NOT NULL DEFAULT 1,   -- next page to fetch on resume
    total_items     INT,                        -- last-seen server total_items
    rows_stored     INT  NOT NULL DEFAULT 0,    -- rows pulled during the walk
    complete        BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, pipeline_name)
);
