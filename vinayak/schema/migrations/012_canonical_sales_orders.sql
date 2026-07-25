-- ============================================================
-- Migration 012 — Canonical layer: Sales Orders
-- ============================================================
-- The sales order book. Like purchase orders, tz_sales_orders is line grain
-- with a per-line order_value and no tax basis, and the panels query it at line
-- grain (open_count = COUNT(*) of open lines, open_value = SUM(order_value),
-- dispatched_pct = dispatched lines / total lines). A single line-grain table
-- keyed on the source raw_id keeps a 1:1 mapping so every count and sum
-- reconciles by construction.
--
-- Object:
--   canon_sales_order          (line grain, one row per SO line)
--   canon_sales_order_flat     (query-facing read model)
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/012_canonical_sales_orders.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS canon_sales_order (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,          -- = source raw_id (1:1 with tz row)
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  order_number   text,
  order_date     date,
  customer_ref   text,                -- customer code where available
  customer_name  text,
  sku_code       text,
  sku_name       text,
  ordered_qty    numeric,
  dispatched_qty numeric,
  pending_qty    numeric,
  order_value    numeric,             -- per-line value (additive)
  delivery_date  date,
  status         text,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_so_company        ON canon_sales_order (company_id);
CREATE INDEX IF NOT EXISTS idx_canon_so_company_status ON canon_sales_order (company_id, status);
CREATE INDEX IF NOT EXISTS idx_canon_so_delivery       ON canon_sales_order (company_id, delivery_date);

-- ── Flat view (query-facing read model) ─────────────────────
-- Column names mirror what queries.py used on tz_sales_orders.
CREATE OR REPLACE VIEW canon_sales_order_flat AS
  SELECT
    company_id,
    order_number,
    order_date,
    customer_name,
    customer_ref AS customer_code,
    sku_code,
    sku_name,
    ordered_qty,
    dispatched_qty,
    pending_qty,
    order_value,
    delivery_date,
    status
  FROM canon_sales_order;

COMMIT;
