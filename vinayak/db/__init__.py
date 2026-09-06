"""
vinayak.db
──────────
The data-access layer. Connection management is encapsulated in the Database
class (db/session.py) instead of being reinvented as a `_conn()` helper in every
route and module. Higher layers depend on this abstraction, not on psycopg2
directly (dependency inversion).
"""
from vinayak.db.session import Database, db

__all__ = ["Database", "db"]
