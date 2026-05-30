"""
scripts/reset_db.py
────────────────────
Full DB reset: wipe all tenant data, re-apply schema, seed admin user.

Usage:
    python -m vinayak.scripts.reset_db [--yes]

Pass --yes to skip the "are you sure?" prompt (for CI / scripted setups).
The script prompts for admin email + password unless ADMIN_EMAIL / ADMIN_PASSWORD
env vars are set (useful for one-shot automation).
"""
from __future__ import annotations

import argparse
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

# Tables that hold per-company data — truncate in dependency order
_DATA_TABLES = [
    "tz_ar_aging",
    "tz_sales_invoices",
    "tz_purchase_invoices",
    "tz_sales_orders",
    "tz_purchase_orders",
    "tz_grn_qir",
    "tz_sales_quotations",
    "tz_inventory_valuation",
    "tz_process_details",
    "tz_process_routing",
    "tz_backfill_state",
    "tz_sync_runs",
    "tool_connections",
    "users",
    "companies",
]


def _apply_schema(conn) -> None:
    sql_path = Path(__file__).parent.parent / "schema" / "init.sql"
    sql = sql_path.read_text()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    logger.info("✓ Schema applied.")


def _wipe_data(conn) -> None:
    with conn.cursor() as cur:
        for table in _DATA_TABLES:
            cur.execute(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = %s)",
                (table,),
            )
            if cur.fetchone()[0]:
                cur.execute(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE" if table.startswith("tz_") else f"DELETE FROM {table}")
                logger.info("  cleared  %s", table)
    conn.commit()
    logger.info("✓ All tenant data wiped.")


def _seed_admin(conn, email: str, password: str) -> None:
    hashed = pwd_context.hash(password)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO users (email, password_hash, role)
               VALUES (%s, %s, 'admin')
               ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash""",
            (email.lower().strip(), hashed),
        )
    conn.commit()
    logger.info("✓ Admin user '%s' seeded.", email)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset DB and seed admin user")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = parser.parse_args()

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL is not set.")
        sys.exit(1)

    if not args.yes:
        confirm = input(
            "\n⚠️  This will DELETE ALL DATA from the database. Type 'yes' to continue: "
        ).strip()
        if confirm != "yes":
            print("Aborted.")
            sys.exit(0)

    logger.info("Connecting…")
    conn = psycopg2.connect(db_url)

    try:
        _apply_schema(conn)
        _wipe_data(conn)

        # Admin credentials — env vars or interactive prompt
        email = os.environ.get("ADMIN_EMAIL") or input("\nAdmin email: ").strip().lower()
        if not email:
            logger.error("Email cannot be empty.")
            sys.exit(1)

        password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password (min 8 chars): ")
        if len(password) < 8:
            logger.error("Password must be at least 8 characters.")
            sys.exit(1)

        _seed_admin(conn, email, password)

        print(f"\n✓ Done. Log in at the dashboard with: {email}")
        print("  (No ADMIN_EMAIL / ADMIN_PASSWORD needed in .env)")

    except Exception as exc:
        conn.rollback()
        logger.error("Reset failed: %s", exc)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
