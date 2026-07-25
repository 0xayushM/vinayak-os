-- ============================================================
-- Migration 011 — Canonical layer: Purchase Orders
-- ============================================================
-- Extends the canonical schema to the purchase-order book. POs are queried
-- purely at LINE grain (open_count = COUNT(*) of open lines, open_value =
-- SUM(po_value)), and po_value is already a per-line value with no tax basis —
-- so a single line-grain table + flat view reconciles the panels exactly.
--
-- The row is keyed on the source raw_id (the content hash the ingestion layer
-- already deduped on), giving a 1:1 mapping with tz_purchase_orders so every
-- count and sum matches by construction.
--
-- Object:
--   canon_purchase_order          (line grain, one row per PO line)
--   canon_purchase_order_flat     (query-facing read model)
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/011_canonical_purchase_orders.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS canon_purchase_order (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,          -- = source raw_id (1:1 with tz row)
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  po_number      text,
  po_date        date,
  vendor_ref     text,                -- vendor code where available
  vendor_name    text,
  item_code      text,
  item_name      text,
  ordered_qty    numeric,
  received_qty   numeric,
  pending_qty    numeric,
  po_value       numeric,             -- per-line value (additive)
  expected_date  date,
  status         text,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_po_company        ON canon_purchase_order (company_id);
CREATE INDEX IF NOT EXISTS idx_canon_po_company_status ON canon_purchase_order (company_id, status);
CREATE INDEX IF NOT EXISTS idx_canon_po_expected       ON canon_purchase_order (company_id, expected_date);

-- ── Flat view (query-facing read model) ─────────────────────
-- Column names mirror what queries.py used on tz_purchase_orders.
CREATE OR REPLACE VIEW canon_purchase_order_flat AS
  SELECT
    company_id,
    po_number,
    po_date,
    vendor_name,
    vendor_ref  AS vendor_code,
    item_code,
    item_name,
    ordered_qty,
    received_qty,
    pending_qty,
    po_value,
    expected_date,
    status
  FROM canon_purchase_order;

COMMIT;
