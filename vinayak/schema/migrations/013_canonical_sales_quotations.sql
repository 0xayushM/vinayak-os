-- ============================================================
-- Migration 013 — Canonical layer: Sales Quotations
-- ============================================================
-- The quote pipeline. tz_sales_quotations is line grain with a per-line
-- quoted_value, a status, and a converted_to_order flag (a quote counts as won
-- once converted or explicitly won/accepted). The panel queries it at line grain
-- over a date window, so a single line-grain table keyed on the source raw_id
-- keeps a 1:1 mapping and the funnel (open/won/conversion) reconciles exactly.
--
-- Object:
--   canon_sales_quotation          (line grain, one row per quote line)
--   canon_sales_quotation_flat     (query-facing read model)
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/013_canonical_sales_quotations.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS canon_sales_quotation (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,          -- = source raw_id (1:1 with tz row)
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  quote_number       text,
  quote_date         date,
  customer_ref       text,            -- customer code where available
  customer_name      text,
  sku_code           text,
  sku_name           text,
  quoted_qty         numeric,
  quoted_value       numeric,         -- per-line value (additive)
  status             text,
  valid_until        date,
  converted_to_order boolean,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_quote_company      ON canon_sales_quotation (company_id);
CREATE INDEX IF NOT EXISTS idx_canon_quote_company_date ON canon_sales_quotation (company_id, quote_date);

-- ── Flat view (query-facing read model) ─────────────────────
-- Column names mirror what queries.py used on tz_sales_quotations.
CREATE OR REPLACE VIEW canon_sales_quotation_flat AS
  SELECT
    company_id,
    quote_number,
    quote_date,
    customer_name,
    customer_ref AS customer_code,
    sku_code,
    sku_name,
    quoted_qty,
    quoted_value,
    status,
    valid_until,
    converted_to_order
  FROM canon_sales_quotation;

COMMIT;
