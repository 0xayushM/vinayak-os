-- ============================================================
-- Migration 005 — Scope chat history to (user, brand)
-- ============================================================
-- Each owner's conversation is private to them within a brand. Adds user_id
-- (the login email) to chat_turn and indexes by (company_id, user_id, time).
-- Existing rows get a placeholder owner so nothing breaks.
-- Idempotent + safe to re-run.
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/005_chat_user_scope.sql
-- ============================================================

BEGIN;

ALTER TABLE chat_turn ADD COLUMN IF NOT EXISTS user_id text;
UPDATE chat_turn SET user_id = 'legacy' WHERE user_id IS NULL;

DROP INDEX IF EXISTS idx_chat_turn_company;
CREATE INDEX IF NOT EXISTS idx_chat_turn_user
  ON chat_turn (company_id, user_id, created_at DESC);

COMMIT;
