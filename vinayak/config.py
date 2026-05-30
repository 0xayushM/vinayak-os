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

# ── TranzAct API endpoints (infrastructure URLs, not credentials) ─────────────
TRANZACT_BASE_URL      = os.getenv("TRANZACT_BASE_URL",      "https://be.letstranzact.com")
# Confirmed 2026-05-22: reports live on a separate reporting subdomain
TRANZACT_REPORTING_URL = os.getenv("TRANZACT_REPORTING_URL", "https://reporting.letstranzact.com")

# ── Postgres ─────────────────────────────────────────────────────────────────
DATABASE_URL = os.environ["DATABASE_URL"]
# e.g. postgresql://user:pass@host:5432/vinayak_brain

# ── Rate-limiting ─────────────────────────────────────────────────────────────
# TranzAct enforces 10 req/min/machine.  We stay comfortably under that.
TRANZACT_REQUESTS_PER_MINUTE = int(os.getenv("TRANZACT_REQUESTS_PER_MINUTE", "8"))

# ── Data freshness alert threshold ───────────────────────────────────────────
# If a pipeline has not completed within this many hours, alert fires.
SYNC_STALENESS_HOURS = int(os.getenv("SYNC_STALENESS_HOURS", "25"))
