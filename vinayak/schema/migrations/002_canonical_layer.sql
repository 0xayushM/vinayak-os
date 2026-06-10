-- ============================================================
-- Migration 002 — Canonical layer (Phase 1, Slice 1)
-- ============================================================
-- Introduces the source-independent canonical schema (Layer 0).
-- The Tranzact-shaped tz_* tables become the FIRST adapter's source;
-- a TranzactCanonicalAdapter maps them into these canon_* tables.
--
-- Slice 1 objects (manufacturing sales/AR/inventory side):
--   canon_customer
--   canon_sales_invoice + canon_sales_invoice_line
--   canon_inventory_item
--   canon_payment            (AR/receivables position from tz_ar_aging)
--
-- Every row carries the universal envelope:
--   id, company_id, source, source_ref, ingested_at, confidence, raw
--
-- ingest_issues logs anything the adapter cannot confidently map —
-- never guess, never silently drop. This table IS the parser backlog.
--
-- Flat VIEWS (canon_*_flat) mirror the columns queries.py already uses
-- so the query layer repoints with a table-name swap and reconciles by
-- construction.
--
-- Idempotent + safe to re-run.
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/002_canonical_layer.sql
-- ============================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- ── Parser backlog ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS ingest_issues (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text,
  object_type text,           -- 'sales_invoice' | 'customer' | 'inventory_item' | 'payment'
  field       text,
  reason      text,           -- 'missing_required' | 'unparseable' | 'orphan_reference' | ...
  raw_value   text,
  created_at  timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_ingest_issues_company ON ingest_issues (company_id, source, created_at DESC);

-- ── canon_customer ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS canon_customer (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  name               text,
  customer_code      text,
  credit_limit       numeric,
  payment_terms_days int,
  outstanding        numeric,
  risk_score         real,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_customer_company ON canon_customer (company_id);

-- ── canon_sales_invoice (header, one row per invoice) ───────
CREATE TABLE IF NOT EXISTS canon_sales_invoice (
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
  customer_ref   text,        -- maps to canon_customer.customer_code
  customer_name  text,
  gross          numeric,     -- sum of line goods value (ex-tax)
  tax            numeric,
  net            numeric,     -- printed invoice grand total (incl tax/freight)
  status         text,
  salesperson    text,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_si_company_date ON canon_sales_invoice (company_id, invoice_date);

-- ── canon_sales_invoice_line ────────────────────────────────
CREATE TABLE IF NOT EXISTS canon_sales_invoice_line (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  invoice_id  uuid REFERENCES canon_sales_invoice(id) ON DELETE CASCADE,
  source      text NOT NULL,
  source_ref  text NOT NULL,
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  invoice_number text,        -- denormalised for trivial flat-view joins
  sku            text,
  sku_name       text,
  category       text,
  quantity       numeric,
  unit_price     numeric,
  line_total     numeric,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_sil_company ON canon_sales_invoice_line (company_id);
CREATE INDEX IF NOT EXISTS idx_canon_sil_invoice ON canon_sales_invoice_line (invoice_id);

-- ── canon_inventory_item (snapshot) ─────────────────────────
CREATE TABLE IF NOT EXISTS canon_inventory_item (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  sku                text,
  sku_name           text,
  category           text,
  warehouse          text,
  quantity           numeric,
  qty_reserved       numeric,
  unit_cost          numeric,
  total_value        numeric,
  is_raw_material    boolean,
  is_negative_stock  boolean,
  last_movement_date date,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_inv_company ON canon_inventory_item (company_id);

-- ── canon_payment (AR / receivables position) ───────────────
CREATE TABLE IF NOT EXISTS canon_payment (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  source      text NOT NULL,
  source_ref  text NOT NULL,
  ingested_at timestamptz DEFAULT now(),
  confidence  real DEFAULT 1.0,
  raw         jsonb,
  customer_ref       text,
  customer_name      text,
  invoice_number     text,
  invoice_date       date,
  due_date           date,
  invoice_amount     numeric,
  outstanding_amount numeric,
  days_overdue       int,
  aging_bucket       text,
  mode               text,
  reconciled         boolean,
  UNIQUE (company_id, source, source_ref)
);
CREATE INDEX IF NOT EXISTS idx_canon_pay_company ON canon_payment (company_id);

-- ── Flat views (query-facing read models) ───────────────────
-- Mirror exactly the column names queries.py used on tz_*.
CREATE OR REPLACE VIEW canon_sales_invoice_flat AS
  SELECT
    l.company_id,
    h.invoice_number,
    h.invoice_date,
    h.due_date,
    h.customer_ref  AS customer_code,
    h.customer_name,
    l.sku           AS sku_code,
    l.sku_name,
    l.category,
    l.quantity,
    l.unit_price,
    l.line_total,
    h.net           AS invoice_total,
    h.status        AS payment_status,
    h.salesperson
  FROM canon_sales_invoice_line l
  JOIN canon_sales_invoice h ON l.invoice_id = h.id;

CREATE OR REPLACE VIEW canon_inventory_flat AS
  SELECT
    company_id,
    sku        AS sku_code,
    sku_name,
    category,
    warehouse,
    quantity,
    unit_cost,
    total_value,
    is_raw_material,
    is_negative_stock
  FROM canon_inventory_item;

CREATE OR REPLACE VIEW canon_ar_flat AS
  SELECT
    company_id,
    customer_name,
    customer_ref AS customer_code,
    invoice_number,
    invoice_date,
    due_date,
    invoice_amount,
    outstanding_amount,
    days_overdue,
    aging_bucket
  FROM canon_payment;

COMMIT;
