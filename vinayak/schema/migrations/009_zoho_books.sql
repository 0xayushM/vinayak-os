-- 009_zoho_books.sql
-- ───────────────────
-- Raw landing tables for the Zoho Books adapter (source #2 — the one that
-- proves the canonical model is genuinely source-agnostic).
--
-- Naming: zb_* mirrors the tz_* convention. Zoho gives every record a stable
-- numeric ID, so upserts key on (company_id, zoho_id) directly — no
-- content-hash workaround needed (unlike TranzAct).
--
-- Bonus columns TranzAct never had: contact email/phone (feeds the marketing
-- engine's customer_contacts) and invoice balance/paid dates (real AR truth).
--
-- Idempotent: safe to run more than once.

CREATE TABLE IF NOT EXISTS zb_contacts (
    company_id     TEXT NOT NULL,
    zoho_id        TEXT NOT NULL,             -- contact_id
    contact_name   TEXT,
    contact_type   TEXT,                      -- customer | vendor
    company_name   TEXT,
    email          TEXT,
    phone          TEXT,
    mobile         TEXT,
    gst_no         TEXT,
    payment_terms  INT,                       -- days
    outstanding_receivable NUMERIC,
    outstanding_payable    NUMERIC,
    status         TEXT,
    raw            JSONB,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, zoho_id)
);

CREATE TABLE IF NOT EXISTS zb_invoices (
    company_id     TEXT NOT NULL,
    zoho_id        TEXT NOT NULL,             -- invoice_id
    invoice_number TEXT,
    customer_id    TEXT,
    customer_name  TEXT,
    invoice_date   DATE,
    due_date       DATE,
    status         TEXT,                      -- draft|sent|overdue|paid|void|partially_paid
    sub_total      NUMERIC,                   -- pre-tax (goods basis)
    tax_total      NUMERIC,
    total          NUMERIC,                   -- invoice grand total
    balance        NUMERIC,                   -- unpaid amount (live AR!)
    last_payment_date DATE,
    raw            JSONB,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, zoho_id)
);
CREATE INDEX IF NOT EXISTS idx_zb_inv_date ON zb_invoices (company_id, invoice_date);

CREATE TABLE IF NOT EXISTS zb_bills (
    company_id     TEXT NOT NULL,
    zoho_id        TEXT NOT NULL,             -- bill_id
    bill_number    TEXT,
    vendor_id      TEXT,
    vendor_name    TEXT,
    bill_date      DATE,
    due_date       DATE,
    status         TEXT,
    sub_total      NUMERIC,
    total          NUMERIC,
    balance        NUMERIC,                   -- what WE still owe (live AP!)
    raw            JSONB,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, zoho_id)
);
CREATE INDEX IF NOT EXISTS idx_zb_bill_date ON zb_bills (company_id, bill_date);

CREATE TABLE IF NOT EXISTS zb_items (
    company_id     TEXT NOT NULL,
    zoho_id        TEXT NOT NULL,             -- item_id
    item_name      TEXT,
    sku            TEXT,
    category       TEXT,                      -- item group / category if present
    rate           NUMERIC,                   -- selling price
    purchase_rate  NUMERIC,                   -- COST — enables real margin later!
    stock_on_hand  NUMERIC,
    unit           TEXT,
    status         TEXT,
    raw            JSONB,
    fetched_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (company_id, zoho_id)
);
