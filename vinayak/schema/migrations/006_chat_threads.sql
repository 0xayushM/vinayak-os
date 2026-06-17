-- ============================================================
-- Migration 006 — Chat threads (Windsurf-style tabs)
-- ============================================================
-- A conversation is now a THREAD (a tab). Each thread belongs to one owner
-- within one brand and holds many turns. Auto-named from its first question.
-- Existing turns are migrated into one "Earlier chat" thread per (brand, user).
-- Idempotent + safe to re-run.
--   psql "$DATABASE_URL" -1 -f vinayak/schema/migrations/006_chat_threads.sql
-- ============================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS chat_thread (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  text NOT NULL,
  user_id     text NOT NULL,
  title       text,
  created_at  timestamptz DEFAULT now(),
  updated_at  timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_chat_thread_user
  ON chat_thread (company_id, user_id, updated_at DESC);

ALTER TABLE chat_turn ADD COLUMN IF NOT EXISTS thread_id uuid;

-- Backfill: one "Earlier chat" thread per (company, user) that has orphan turns.
DO $$
DECLARE r RECORD; tid uuid;
BEGIN
  FOR r IN
    SELECT DISTINCT company_id, user_id FROM chat_turn WHERE thread_id IS NULL
  LOOP
    INSERT INTO chat_thread (company_id, user_id, title)
    VALUES (r.company_id, r.user_id, 'Earlier chat')
    RETURNING id INTO tid;
    UPDATE chat_turn SET thread_id = tid
      WHERE company_id = r.company_id AND user_id = r.user_id AND thread_id IS NULL;
  END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_chat_turn_thread ON chat_turn (thread_id, created_at);

COMMIT;
