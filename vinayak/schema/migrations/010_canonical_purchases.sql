-- ============================================================
-- Migration 010 — Canonical layer: Purchases
-- ============================================================
-- Extends the canonical schema (migration 002) to the purchase side,
-- mirroring canon_sales_invoice(+_line) exactly so the query layer
-- repoints from tz_purchase_invoices with a table-name swap and
-- reconciles by construction.
--
-- Objects:
--   canon_purchase_invoice        (header, one row per purchase invoice)
--   canon_purchase_invoice_line   (line items)
--   canon_purchase_invoice_flat   (query-facing read model)
--
-- The tax rule matches sales: TranzAct's line value (item_total_value) is
-- TAX-INCLUSIVE, so the canonical `gross`/line `line_total` are stored
-- EX-TAX (line_incl - tax); `net` is the printed grand total (incl tax).
-- The query layer therefore reads line_total as goods value directly —
-- no goods_ex_tax subtraction needed (same as the sales flat view).
--
-- Idempotent + safe to re-run:
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/010_canonical_purchases.sql
-- ============================================================

BEGIN;

-- ── canon_purchase_invoice (header, one row per invoice) ────
CREATE TABLE IF NOT EXISTS canon_purchase_invoice (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  invoice_number text,
  invoice_date   date,
  due_date       date,
  vendor_ref     text,        -- maps to a vendor code where available
  vendor_name    text,
  gross          numeric,     -- sum of line goods value (ex-tax)
  tax            numeric,
  net            numeric,     -- printed invoice grand total (incl tax/freight)
  status         text,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_pi_company_date
  ON canon_purchase_invoice (company_id, invoice_date);

-- ── canon_purchase_invoice_line ─────────────────────────────
CREATE TABLE IF NOT EXISTS canon_purchase_invoice_line (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  invoice_id  uuid REFERENCES canon_purchase_invoice(id) ON DELETE CASCADE,
  source      text NOT NULL,
  source_ref  text NOT NULL,
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  invoice_number text,        -- denormalised for trivial flat-view joins
  sku            text,        -- item_code
  sku_name       text,        -- item_name
  quantity       numeric,
  unit_price     numeric,
  line_total     numeric,     -- EX-TAX goods value
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_pil_company ON canon_purchase_invoice_line (company_id);
CREATE INDEX IF NOT EXISTS idx_canon_pil_invoice ON canon_purchase_invoice_line (invoice_id);

-- ── Flat view (query-facing read model) ─────────────────────
-- Column names mirror what queries.py used on tz_purchase_invoices:
--   invoice_date, invoice_number, vendor_name, vendor_code,
--   item_code, item_name, quantity, unit_price, line_total, invoice_total
CREATE OR REPLACE VIEW canon_purchase_invoice_flat AS
  SELECT
    l.company_id,
    h.invoice_number,
    h.invoice_date,
    h.due_date,
    h.vendor_name,
    h.vendor_ref    AS vendor_code,
    l.sku           AS item_code,
    l.sku_name      AS item_name,
    l.quantity,
    l.unit_price,
    l.line_total,                 -- ex-tax goods value
    h.net           AS invoice_total
  FROM canon_purchase_invoice_line l
  JOIN canon_purchase_invoice h ON l.invoice_id = h.id;

COMMIT;
