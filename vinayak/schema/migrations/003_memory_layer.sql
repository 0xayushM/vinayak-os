-- ============================================================
-- Migration 003 — Context & Memory (Phase 2, Layer 2)
-- ============================================================
-- The deeper moat: a static business profile seeded at onboarding,
-- and a durable, decaying memory of facts the owner reveals.
--
--   business_profile  — one row per company, loaded on every query
--   memory_fact       — durable facts; supersede + decay correctly
--
-- The DB is the source of truth. The customers/<name>.md renders are
-- a read-only VIEW of the active facts, never the write target.
--
-- Idempotent + safe to re-run.
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/003_memory_layer.sql
-- ============================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Static business profile (seeded at onboarding) ──────────
CREATE TABLE IF NOT EXISTS business_profile (
  company_id         text PRIMARY KEY,
  industry           text,
  sub_vertical       text,          -- trading | manufacturing | retail | services
  fiscal_year_start  text,          -- 'MM-DD', e.g. '04-01' for India
  gst_registered     boolean,
  base_currency      text DEFAULT 'INR',
  healthy_margin_pct real,
  seasonality        text,          -- free text: 'Diwali spike, Q4 push'
  key_customers      jsonb,         -- [{name, note, payment_terms_days}]
  kpis               text,          -- which KPIs the owner cares about
  extras             jsonb,         -- vertical-specific catch-all
  updated_at         timestamptz DEFAULT now()
);

-- ── Memory facts (durable, decaying) ────────────────────────
CREATE TABLE IF NOT EXISTS memory_fact (
  id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id        text NOT NULL,
  entity_type       text,           -- 'customer' | 'item' | 'company'
  entity_ref        text,           -- 'customer:dev-colour'
  claim_key         text,           -- 'payment_terms_days'
  claim_value       jsonb,          -- 60
  origin            text,           -- 'user_confirmed' | 'ai_inferred' | 'imported'
  confidence        real DEFAULT 1.0,
  created_at        timestamptz DEFAULT now(),
  source_msg_id     uuid,           -- chat turn it came from (provenance)
  valid_until       timestamptz,    -- when to re-check (null = no expiry)
  last_validated_at timestamptz,
  status            text DEFAULT 'active',  -- 'active' | 'stale' | 'superseded'
  superseded_by     uuid,
  stale_reason      text
);
CREATE INDEX IF NOT EXISTS idx_memory_fact_lookup
  ON memory_fact (company_id, entity_ref, claim_key, status);
CREATE INDEX IF NOT EXISTS idx_memory_fact_company
  ON memory_fact (company_id, status);

COMMIT;
