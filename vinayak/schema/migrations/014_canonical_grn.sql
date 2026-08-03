-- ============================================================
-- Migration 014 — Canonical layer: GRN / QIR (goods received + inspection)
-- ============================================================
-- tz_grn_qir is line grain (received qty + inspection outcome per item). The
-- panel counts distinct GRNs, sums received/rejected qty, and — critically —
-- treats a NULL rejected_qty as "received but not yet inspected" (pending_qir).
-- So the canonical mapping must PRESERVE NULLs, never coerce a missing rejection
-- decision to 0. Keyed on the source raw_id for an exact 1:1 mapping.
--
-- Report 34 carries quantities but no monetary value, so there is no value
-- column here (the panel reports total_value = 0).
--
-- Object:
--   canon_grn          (line grain, one row per GRN/QIR line)
--   canon_grn_flat     (query-facing read model)
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/014_canonical_grn.sql
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS canon_grn (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,          -- = source raw_id (1:1 with tz row)
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  grn_number   text,
  grn_date     date,
  vendor_ref   text,                  -- vendor code where available
  vendor_name  text,
  po_number    text,
  item_code    text,
  item_name    text,
  ordered_qty  numeric,
  received_qty numeric,
  rejected_qty numeric,               -- NULL = not yet inspected (pending QIR)
  accepted_qty numeric,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_grn_company      ON canon_grn (company_id);
CREATE INDEX IF NOT EXISTS idx_canon_grn_company_date ON canon_grn (company_id, grn_date);

-- ── Flat view (query-facing read model) ─────────────────────
-- Column names mirror what queries.py used on tz_grn_qir.
CREATE OR REPLACE VIEW canon_grn_flat AS
  SELECT
    company_id,
    grn_number,
    grn_date,
    vendor_name,
    vendor_ref AS vendor_code,
    po_number,
    item_code,
    item_name,
    ordered_qty,
    received_qty,
    rejected_qty,
    accepted_qty
  FROM canon_grn;

COMMIT;
