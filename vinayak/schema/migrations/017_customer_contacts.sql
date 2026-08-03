-- ============================================================
-- Migration 017 — customer_contacts
-- ============================================================
-- Where to reach a customer. TranzAct carries no contact data, so this is filled
-- manually (or from Zoho's zb_contacts, which does have email/phone). Keyed on the
-- customer NAME so it lines up with canon_ar_flat.customer_name used everywhere.
--
-- The action spine reads this at approval time to know where to send a reminder;
-- no send happens without a recipient here.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS customer_contacts (
  company_id   text NOT NULL,
  customer_ref text NOT NULL,       -- customer name (matches canon_ar_flat.customer_name)
  email        text,
  phone        text,
  source       text,                -- 'manual' | 'zoho' | 'import'
  updated_at   timestamptz DEFAULT now(),
  PRIMARY KEY (company_id, customer_ref)
);

COMMIT;
