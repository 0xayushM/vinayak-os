"""
scripts/setup_db.py
────────────────────
One-shot setup: applies schema/init.sql then creates the initial admin user.

Usage:
    python -m vinayak.scripts.setup_db

Run this ONCE before starting the server for the first time.
Safe to re-run — schema uses IF NOT EXISTS; admin creation skips if email exists.

No admin credentials are needed in environment variables after this runs.
"""
from __future__ import annotations

import getpass
import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from passlib.context import CryptContext

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _apply_schema(conn) -> None:
    sql_path = Path(__file__).parent.parent / "schema" / "init.sql"
    if not sql_path.exists():
        logger.error("schema/init.sql not found at %s", sql_path)
        sys.exit(1)
    sql = sql_path.read_text()
    with conn.cursor() as cur:
        logger.info("Applying schema/init.sql…")
        cur.execute(sql)
    conn.commit()
    logger.info("✓ Schema applied.")


def _verify_tables(conn) -> None:
    tables = [
        "companies", "users", "tool_connections",
        "tz_sales_invoices", "tz_ar_aging", "tz_inventory_valuation",
        "tz_sync_runs",
    ]
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                (table,),
            )
            exists = cur.fetchone()[0]
            logger.info("  %s  %s", "✓" if exists else "✗ MISSING", table)


def _create_admin(conn) -> None:
    print("\n── Create admin user ─────────────────────────────")
    email = input("Admin email: ").strip().lower()
    if not email:
        logger.error("Email cannot be empty.")
        sys.exit(1)

    # Check if user already exists
    with conn.cursor() as cur:
        cur.execute("SELECT id, password_hash FROM users WHERE LOWER(email) = %s", (email,))
        existing = cur.fetchone()

    if existing and existing[1]:
        overwrite = input(f"User '{email}' already has a password. Reset it? [y/N] ").strip().lower()
        if overwrite != "y":
            logger.info("Skipped — existing admin kept.")
            return

    password = getpass.getpass("Admin password: ")
    if len(password) < 8:
        logger.error("Password must be at least 8 characters.")
        sys.exit(1)
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        logger.error("Passwords do not match.")
        sys.exit(1)

    hashed = pwd_context.hash(password)

    with conn.cursor() as cur:
        if existing:
            cur.execute(
                "UPDATE users SET password_hash = %s WHERE LOWER(email) = %s",
                (hashed, email),
            )
        else:
            cur.execute(
                """INSERT INTO users (email, password_hash, role)
                   VALUES (%s, %s, 'admin')""",
                (email, hashed),
            )
    conn.commit()
    logger.info("✓ Admin user '%s' created/updated.", email)
    print("\nYou can now log in at the dashboard with this email and password.")
    print("Do NOT add ADMIN_EMAIL or ADMIN_PASSWORD to your .env — "
          "credentials are stored in the database.")


def main() -> None:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL is not set. Check your .env file.")
        sys.exit(1)

    logger.info("Connecting to database…")
    try:
        conn = psycopg2.connect(db_url)
    except Exception as exc:
        logger.error("Could not connect: %s", exc)
        sys.exit(1)

    try:
        _apply_schema(conn)
        _verify_tables(conn)
        _create_admin(conn)
    except Exception as exc:
        conn.rollback()
        logger.error("Setup failed: %s", exc)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
