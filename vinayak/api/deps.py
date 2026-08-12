"""
api/deps.py
────────────
The single home for shared FastAPI dependencies, so route modules import them
from one place instead of each re-deriving a DB helper. As dashboard.py is split
into domain route modules, every one of them will pull `get_db`,
`get_current_user`, and `require_workspace` from here.

  • get_db()            — a connection via the shared Database gateway, 503 on failure
  • get_current_user    — JWT → TokenPayload           (re-exported from routes.auth)
  • require_workspace   — resolve + authorise company_id (re-exported from routes.workspaces)
"""
from __future__ import annotations

import logging

import psycopg2
from fastapi import HTTPException

from vinayak.db.session import db
# Re-export the auth/tenancy dependencies so routes have one import surface.
from vinayak.api.routes.auth import get_current_user, TokenPayload  # noqa: F401
from vinayak.api.routes.workspaces import require_workspace  # noqa: F401

logger = logging.getLogger(__name__)


def get_db():
    """Open a request connection through the shared Database gateway. Caller owns
    its lifecycle (matches the previous per-route `_conn()` contract)."""
    try:
        return db.connect()
    except psycopg2.OperationalError as exc:
        logger.error("DB connection failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Database unavailable — check DATABASE_URL (Supabase direct connection, port 5432)",
        ) from exc
