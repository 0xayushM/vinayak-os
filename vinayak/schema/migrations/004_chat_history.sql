-- ============================================================
-- Migration 004 — Chat history (Phase 3 UX)
-- ============================================================
-- Persists each Ask turn (question + full structured answer) per workspace so
-- the conversation survives reloads. Scoped by company_id like everything else.
-- Idempotent + safe to re-run.
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/004_chat_history.sql
-- ============================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS chat_turn (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  question    text NOT NULL,
  answer      jsonb NOT NULL,        -- the full structured Answer dict
  created_at  timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_turn_company ON chat_turn (company_id, created_at DESC);

COMMIT;
