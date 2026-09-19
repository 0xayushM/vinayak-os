"""
config.py — environment configuration for Vinayak Brain OS
All values come from environment variables or a .env file.
Never hard-code credentials here.

Credentials that are NO LONGER in env:
  - TRANZACT_EMAIL / TRANZACT_PASSWORD  → stored encrypted per brand in DB (tool_connections)
  - ADMIN_EMAIL / ADMIN_PASSWORD        → stored hashed in DB (users.password_hash)
  - DEFAULT_COMPANY_ID                  → workspace resolved at request time from DB
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Environment mode ──────────────────────────────────────────────────────────
# VINAYAK_DEV_MODE=1 relaxes the fail-hard security checks for local dev only
# (ephemeral JWT secret, optional internal key, localhost CORS). NEVER set it
# in production.
DEV_MODE = os.getenv("VINAYAK_DEV_MODE", "").strip().lower() in ("1", "true", "yes")

# ── TranzAct API endpoints (infrastructure URLs, not credentials) ─────────────
TRANZACT_BASE_URL      = os.getenv("TRANZACT_BASE_URL",      "https://be.letstranzact.com")
# Confirmed 2026-05-22: reports live on a separate reporting subdomain
TRANZACT_REPORTING_URL = os.getenv("TRANZACT_REPORTING_URL", "https://reporting.letstranzact.com")

def env_int(name: str, default: int) -> int:
    """An integer setting, where blank means "not set". A host that passes an
    empty value through (a Railway reference to a variable the other service
    never defined) must fall back to the default, not stop the process."""
    raw = (os.getenv(name) or "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


# ── Postgres ─────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ["DATABASE_URL"]
# e.g. postgresql://user:pass@host:5432/vinayak_brain

# ── Rate-limiting ─────────────────────────────────────────────────────────────
# TranzAct enforces 10 req/min/machine.  We stay comfortably under that.
TRANZACT_REQUESTS_PER_MINUTE = env_int("TRANZACT_REQUESTS_PER_MINUTE", 8)

# ── Data freshness alert threshold ───────────────────────────────────────────
# If a pipeline has not completed within this many hours, alert fires.
SYNC_STALENESS_HOURS = env_int("SYNC_STALENESS_HOURS", 25)

# ── Claude / Anthropic (optional — Layer 3 reasoning) ────────────────────────
# When ANTHROPIC_API_KEY is set, the reasoning engine uses Claude to ROUTE
# unrecognised questions and to PHRASE answers from already-validated claims.
# Numbers stay deterministic regardless; without a key the engine still works.
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
# Two-tier model routing to control cost: cheap+fast model for simple factual
# lookups (the default), strong model only when a question needs analysis,
# judgment, or fell outside the keyword router.
ANTHROPIC_MODEL_FAST  = os.getenv("ANTHROPIC_MODEL_FAST",  "claude-haiku-4-5")
ANTHROPIC_MODEL_SMART = os.getenv("ANTHROPIC_MODEL_SMART", "claude-sonnet-4-6")
# Back-compat single override (if set, used as the SMART model).
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", ANTHROPIC_MODEL_SMART)

# ── Supabase Auth ─────────────────────────────────────────────────────────────
# Auth is delegated to Supabase (GoTrue). When SUPABASE_JWT_SECRET is set, the
# backend VERIFIES Supabase-issued JWTs (it no longer issues its own) — this flips
# the auth layer from the legacy custom JWT to Supabase, with no other changes.
# Until it is set, the legacy email+password/JWT path stays active (no breakage).
#   • SUPABASE_URL / SUPABASE_ANON_KEY   — used by the frontend Supabase client
#   • SUPABASE_SERVICE_ROLE_KEY          — used ONLY by the one-off user migration
#   • SUPABASE_JWT_SECRET                — the project's JWT secret (HS256) the
#                                          backend verifies access tokens against
SUPABASE_URL              = os.getenv("SUPABASE_URL", "")
SUPABASE_ANON_KEY         = os.getenv("SUPABASE_ANON_KEY", "")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_JWT_SECRET       = os.getenv("SUPABASE_JWT_SECRET", "")
