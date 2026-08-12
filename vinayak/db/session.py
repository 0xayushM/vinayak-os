"""
db/session.py
──────────────
Encapsulates Postgres connection management in one place. Previously every API
route defined its own `def _conn(): return psycopg2.connect(DATABASE_URL)` (four
identical copies) and canonical/pipeline/query modules called psycopg2 directly.

`Database.connect()` returns a raw psycopg2 connection, so existing call sites
that do `conn.cursor()` / `conn.commit()` / `conn.close()` keep working
unchanged. New code should prefer the `cursor()` context manager, which handles
commit/rollback/close automatically.
"""
from __future__ import annotations

from contextlib import contextmanager

import psycopg2

from vinayak.config import DATABASE_URL


class Database:
    """A thin, encapsulated gateway to Postgres. One instance (`db`) is shared."""

    def __init__(self, dsn: str) -> None:
        self._dsn = dsn

    def connect(self, **kwargs):
        """Open a new connection. Caller owns its lifecycle (matches the old
        `_conn()` contract exactly)."""
        return psycopg2.connect(self._dsn, **kwargs)

    @contextmanager
    def cursor(self, commit: bool = False):
        """Managed cursor: commits (if requested) on success, rolls back on error,
        always closes. Preferred for new code."""
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                yield cur
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


# The shared instance every layer uses.
db = Database(DATABASE_URL)
