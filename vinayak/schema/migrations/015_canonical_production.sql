-- ============================================================
-- Migration 015 — Canonical layer: Production + Routing (BOM)
-- ============================================================
-- The last two source feeds. Both are line grain and keyed on the source raw_id
-- for an exact 1:1 mapping so every panel figure reconciles by construction:
--
--   canon_production   ← tz_process_details   (one row per work-order operation:
--                         planned/produced/rejected qty + status). Numeric NULLs
--                         are preserved so the "completed" test
--                         (planned_qty > 0 AND produced_qty >= planned_qty) and
--                         the WIP job counts behave exactly as before.
--   canon_routing      ← tz_process_routing   (one row per routing step). Powers
--                         BOM coverage = manufactured SKUs that have a routing.
--
-- Flat views mirror the columns queries.py used on the tz_* tables.
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/015_canonical_production.sql
-- ============================================================

BEGIN;

-- ── canon_production (one row per work-order operation) ─────
CREATE TABLE IF NOT EXISTS canon_production (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,          -- = source raw_id (1:1 with tz row)
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  production_date   date,
  work_order_number text,
  sku_code          text,
  sku_name          text,
  process_name      text,
  planned_qty       numeric,
  produced_qty      numeric,
  rejected_qty      numeric,
  status            text,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_prod_company        ON canon_production (company_id);
CREATE INDEX IF NOT EXISTS idx_canon_prod_company_date   ON canon_production (company_id, production_date);
CREATE INDEX IF NOT EXISTS idx_canon_prod_company_status ON canon_production (company_id, status);

CREATE OR REPLACE VIEW canon_production_flat AS
  SELECT
    company_id, production_date, work_order_number, sku_code, sku_name,
    process_name, planned_qty, produced_qty, rejected_qty, status
  FROM canon_production;

-- ── canon_routing (one row per routing step) ────────────────
CREATE TABLE IF NOT EXISTS canon_routing (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,          -- = source raw_id (1:1 with tz row)
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  sku_code        text,
  sku_name        text,
  process_name    text,
  sequence_number int,
  standard_hours  numeric,
  machine_centre  text,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_routing_company ON canon_routing (company_id);
CREATE INDEX IF NOT EXISTS idx_canon_routing_sku     ON canon_routing (company_id, sku_code);

CREATE OR REPLACE VIEW canon_routing_flat AS
  SELECT
    company_id, sku_code, sku_name, process_name,
    sequence_number, standard_hours, machine_centre
  FROM canon_routing;

COMMIT;
