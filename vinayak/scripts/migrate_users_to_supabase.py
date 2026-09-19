"""
scripts/migrate_users_to_supabase.py
──────────────────────────────────────
One-off migration: create a Supabase Auth (auth.users) account for every row in
the legacy `users` table, preserving the email → company_id mapping.

bcrypt hashes can't be imported into GoTrue, so each account is created
email-confirmed WITHOUT a password; users set one via the password-reset flow
(the script can trigger recovery emails). The `users` table is kept as the
profile/company-mapping table the backend reads after cutover.

Prerequisites (env):
    SUPABASE_URL                (https://<ref>.supabase.co)
    SUPABASE_SERVICE_ROLE_KEY   (service_role key — NEVER ship to the browser)
    DATABASE_URL

Usage:
    PYTHONPATH=. python -m vinayak.scripts.migrate_users_to_supabase          # dry run
    PYTHONPATH=. python -m vinayak.scripts.migrate_users_to_supabase --apply  # create users
    PYTHONPATH=. python -m vinayak.scripts.migrate_users_to_supabase --apply --send-reset
"""
from __future__ import annotations

import sys

import requests
from dotenv import load_dotenv

load_dotenv()

from vinayak.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, DATABASE_URL  # noqa: E402


def _legacy_users() -> list[tuple[str, str]]:
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT email, COALESCE(company_id, '') FROM users ORDER BY email")
            return [(r[0], r[1]) for r in cur.fetchall()]
    finally:
        conn.close()


def _admin_headers() -> dict:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _create_user(email: str, company_id: str) -> tuple[bool, str]:
    resp = requests.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=_admin_headers(),
        json={
            "email": email,
            "email_confirm": True,                       # no confirmation email needed
            "user_metadata": {"company_id": company_id},  # convenience; source of truth stays `users`
        },
        timeout=20,
    )
    if resp.status_code in (200, 201):
        return True, "created"
    if resp.status_code == 422 and "already been registered" in resp.text:
        return True, "already exists"
    return False, f"{resp.status_code}: {resp.text[:160]}"


def _send_reset(email: str) -> None:
    requests.post(
        f"{SUPABASE_URL}/auth/v1/recover",
        headers={"apikey": SUPABASE_SERVICE_ROLE_KEY, "Content-Type": "application/json"},
        json={"email": email}, timeout=20,
    )


def main() -> int:
    apply = "--apply" in sys.argv
    send_reset = "--send-reset" in sys.argv
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        print("ERROR: set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in the environment.")
        return 2

    users = _legacy_users()
    print(f"{len(users)} legacy users found.{'' if apply else '  (dry run — pass --apply to create)'}")
    for email, company_id in users:
        if not apply:
            print(f"  would create: {email}  → company_id={company_id or '(admin)'}")
            continue
        ok, msg = _create_user(email, company_id)
        print(f"  {email:35s} {msg}")
        if ok and send_reset:
            _send_reset(email)
            print(f"    ↳ password-reset email sent")
    if apply:
        print("\nDone. Users set their password via the reset link. The backend maps "
              "email → company_id from the `users` table, so access is preserved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
