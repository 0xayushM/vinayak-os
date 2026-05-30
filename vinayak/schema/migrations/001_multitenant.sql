-- ============================================================
-- Migration 001 — Multi-tenant isolation
-- ============================================================
-- Adds company_id (the workspace / brand key) to every tz_ data
-- table, switches each table's primary key from (raw_id) to
-- (company_id, raw_id), and tags ALL existing rows as 'protegere'
-- (the crm@protegere.in TranzAct account that fetched them).
--
-- Also re-points the existing 'kbrushes' workspace metadata to the
-- 'protegere' brand and adds owner_id to companies for future
-- multi-owner support.
--
-- Idempotent + safe to re-run. Run inside a transaction:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/001_multitenant.sql
--
-- ⚠️  Take a database snapshot before running — this rewrites
--     primary keys on tables that already hold data.
-- ============================================================

BEGIN;

-- ── 1. Brand (workspace) metadata ───────────────────────────
-- owner_id lets one owner own many brands. NULL = owned by the
-- single configured admin (single-owner mode).
ALTER TABLE companies ADD COLUMN IF NOT EXISTS owner_id TEXT;

-- Seed the real first brand: Protegere.
INSERT INTO companies (id, name)
VALUES ('protegere', 'Protegere')
ON CONFLICT (id) DO NOTHING;

-- Re-point existing connection / sync / backfill rows that were
-- saved under the placeholder 'kbrushes' id to the real brand.
UPDATE tool_connections  SET company_id = 'protegere' WHERE company_id = 'kbrushes';
UPDATE tz_sync_runs      SET company_id = 'protegere' WHERE company_id = 'kbrushes';
UPDATE tz_backfill_state SET company_id = 'protegere' WHERE company_id = 'kbrushes';

-- ── 2. Per-table: add company_id, tag existing rows, swap PK ──
-- A helper DO block applied to every tz_ data table.
DO $$
DECLARE
    tbl  TEXT;
    tbls TEXT[] := ARRAY[
        'tz_sales_invoices',
        'tz_ar_aging',
        'tz_sales_orders',
        'tz_purchase_invoices',
        'tz_purchase_orders',
        'tz_grn_qir',
        'tz_sales_quotations',
        'tz_inventory_valuation',
        'tz_process_routing',
        'tz_process_details'
    ];
BEGIN
    FOREACH tbl IN ARRAY tbls LOOP
        -- 2a. Add the column (nullable first so the backfill can run).
        EXECUTE format(
            'ALTER TABLE %I ADD COLUMN IF NOT EXISTS company_id TEXT', tbl
        );

        -- 2b. Tag every existing (untagged) row as Protegere.
        EXECUTE format(
            'UPDATE %I SET company_id = ''protegere'' WHERE company_id IS NULL', tbl
        );

        -- 2c. Enforce NOT NULL + a safety default for in-flight writes.
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN company_id SET DEFAULT ''protegere''', tbl
        );
        EXECUTE format(
            'ALTER TABLE %I ALTER COLUMN company_id SET NOT NULL', tbl
        );

        -- 2d. Swap the primary key: (raw_id) -> (company_id, raw_id).
        EXECUTE format(
            'ALTER TABLE %I DROP CONSTRAINT IF EXISTS %I', tbl, tbl || '_pkey'
        );
        EXECUTE format(
            'ALTER TABLE %I ADD CONSTRAINT %I PRIMARY KEY (company_id, raw_id)',
            tbl, tbl || '_pkey'
        );

        -- 2e. Index for the common "this brand's rows" filter.
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I (company_id)',
            'idx_' || tbl || '_company', tbl
        );
    END LOOP;
END $$;

-- ── 3. Composite (company_id, date) indexes for hot queries ──
CREATE INDEX IF NOT EXISTS idx_si_company_date
    ON tz_sales_invoices (company_id, invoice_date DESC);
CREATE INDEX IF NOT EXISTS idx_pi_company_date
    ON tz_purchase_invoices (company_id, invoice_date DESC);
CREATE INDEX IF NOT EXISTS idx_so_company_delivery
    ON tz_sales_orders (company_id, delivery_date);
CREATE INDEX IF NOT EXISTS idx_po_company_expected
    ON tz_purchase_orders (company_id, expected_date);
CREATE INDEX IF NOT EXISTS idx_grn_company_date
    ON tz_grn_qir (company_id, grn_date DESC);
CREATE INDEX IF NOT EXISTS idx_quote_company_date
    ON tz_sales_quotations (company_id, quote_date DESC);
CREATE INDEX IF NOT EXISTS idx_pd_company_date
    ON tz_process_details (company_id, production_date DESC);

-- ── 4. Scope sync-run / backfill lookups by brand ────────────
CREATE INDEX IF NOT EXISTS idx_sync_runs_company_pipeline
    ON tz_sync_runs (company_id, pipeline_name, completed_at DESC);

COMMIT;

-- Verify:
--   SELECT company_id, COUNT(*) FROM tz_sales_invoices GROUP BY 1;
--   -- expect a single 'protegere' group with all existing rows.
