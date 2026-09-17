"""
scripts/migrate.py
───────────────────
Applies the migrations in vinayak/schema/migrations that this database has not
seen yet, in filename order, each in its own transaction, recording what ran.

    python -m vinayak.scripts.migrate            # apply what is pending
    python -m vinayak.scripts.migrate --status   # list, change nothing
    python -m vinayak.scripts.migrate --baseline # mark all as applied

Why this exists: for a long time "run the migrations" was something a person
remembered to do, and twice in one day a live database was missing one. The
symptoms were never "a migration is missing" — they were a blank Today page
and an empty Approvals inbox, because a query against a table that does not
exist raises, and code that catches broadly renders the failure as nothing at
all. A ledger turns that into a one-line answer.

Every migration in this repo is written to be idempotent, so re-running one is
safe; the ledger is about knowing, not about protection.

--baseline is for the first run against a database that was migrated by hand:
it records every file as applied without executing anything. Use it once, on a
database you know is current, and never again.
"""
from __future__ import annotations

import hashlib
import pathlib
import sys
import time

import psycopg2

from vinayak.config import DATABASE_URL

MIGRATIONS = pathlib.Path(__file__).resolve().parent.parent / "schema" / "migrations"

LEDGER = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename    TEXT PRIMARY KEY,
    checksum    TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    duration_ms INTEGER
)
"""


def _files() -> list[pathlib.Path]:
    return sorted(MIGRATIONS.glob("*.sql"))


def _checksum(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def _applied(conn) -> dict[str, str]:
    with conn.cursor() as cur:
        cur.execute(LEDGER)
        conn.commit()
        cur.execute("SELECT filename, checksum FROM schema_migrations")
        return dict(cur.fetchall())


def status(conn) -> list[tuple[pathlib.Path, str]]:
    """Every migration with one of: applied · pending · changed."""
    applied = _applied(conn)
    out = []
    for p in _files():
        if p.name not in applied:
            out.append((p, "pending"))
        elif applied[p.name] != _checksum(p):
            out.append((p, "changed"))
        else:
            out.append((p, "applied"))
    return out


def pending(conn) -> list[pathlib.Path]:
    return [p for p, s in status(conn) if s == "pending"]


def apply(conn, p: pathlib.Path) -> int:
    """Run one migration and record it. Returns milliseconds taken."""
    started = time.monotonic()
    sql = p.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    ms = int((time.monotonic() - started) * 1000)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO schema_migrations (filename, checksum, duration_ms)
               VALUES (%s, %s, %s)
               ON CONFLICT (filename) DO UPDATE
                 SET checksum = EXCLUDED.checksum, applied_at = NOW(),
                     duration_ms = EXCLUDED.duration_ms""",
            (p.name, _checksum(p), ms))
    conn.commit()
    return ms


def baseline(conn) -> int:
    """Record every migration as applied without running anything."""
    n = 0
    with conn.cursor() as cur:
        cur.execute(LEDGER)
        for p in _files():
            cur.execute(
                """INSERT INTO schema_migrations (filename, checksum, duration_ms)
                   VALUES (%s, %s, 0) ON CONFLICT (filename) DO NOTHING""",
                (p.name, _checksum(p)))
            n += cur.rowcount or 0
    conn.commit()
    return n


def main(argv: list[str]) -> int:
    conn = psycopg2.connect(DATABASE_URL)
    try:
        if "--baseline" in argv:
            n = baseline(conn)
            print(f"Recorded {n} migration(s) as applied. Nothing was executed.")
            return 0

        rows = status(conn)
        if "--status" in argv:
            for p, s in rows:
                mark = {"applied": "·", "pending": "→", "changed": "!"}[s]
                print(f" {mark} {p.name:45} {s}")
            todo = sum(1 for _, s in rows if s == "pending")
            print(f"\n{todo} pending." if todo else "\nUp to date.")
            return 1 if todo else 0

        todo = [p for p, s in rows if s == "pending"]
        if not todo:
            print("Up to date.")
            return 0
        for p in todo:
            try:
                ms = apply(conn, p)
                print(f" ✓ {p.name} ({ms}ms)")
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                print(f" ✗ {p.name}\n   {exc}", file=sys.stderr)
                print("Stopped. Nothing after this was applied.", file=sys.stderr)
                return 1
        print(f"\nApplied {len(todo)} migration(s).")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
