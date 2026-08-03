-- ============================================================
-- Migration 016 — entity_summary (reason once at ingest)
-- ============================================================
-- A per-entity pre-built view refreshed after each sync, so a question about a
-- customer loads ONE summary instead of re-deriving from rows, and the
-- dashboard's entity pages come free from rendered_md. The structured-plane
-- equivalent of a wiki page.
--
-- summary (jsonb): outstanding, overdue, aging, revenue, last activity, active
--                  memory facts, and any open contradictions (e.g. stated
--                  payment terms vs. how late invoices actually run).
-- rendered_md    : a human-readable rendering of the same, loadable into AI
--                  context or a customer detail page.
--
-- Idempotent + safe to re-run.
-- ============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS entity_summary (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id   text NOT NULL,
  entity_type  text NOT NULL,          -- 'customer'
  entity_ref   text NOT NULL,          -- 'customer:<code>'
  summary      jsonb,
  rendered_md  text,
  refreshed_at timestamptz DEFAULT now(),
  UNIQUE (company_id, entity_type, entity_ref)
);
CREATE INDEX IF NOT EXISTS idx_entity_summary_company
  ON entity_summary (company_id, entity_type);

COMMIT;
