"""
notify.py
──────────
Outbound channel + contact book for the action spine. Two jobs:

  • contacts — where to reach a customer (customer_contacts). Filled manually or
    auto-populated from Zoho's zb_contacts.
  • send_email — deliver an approved message via Resend (HTTP) or SMTP, chosen by
    env. If NEITHER is configured it returns {"sent": False, ...} cleanly — the
    approval still records, it just isn't delivered. So the loop works before the
    env vars are set, and starts sending the moment they are.

Env (set later):
  RESEND_API_KEY            → use Resend
  SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD → use SMTP
  EMAIL_FROM                → From header (default a safe no-reply)
"""
from __future__ import annotations

import logging
import os
import smtplib
import ssl
from email.message import EmailMessage

logger = logging.getLogger(__name__)


# ── contacts ──────────────────────────────────────────────────────────────────
def get_contact_email(conn, company_id: str, customer_ref: str) -> str | None:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT email FROM customer_contacts WHERE company_id = %s AND customer_ref = %s",
            (company_id, customer_ref),
        )
        row = cur.fetchone()
    return row[0] if row and row[0] else None


def upsert_contact(conn, company_id: str, customer_ref: str,
                   email: str | None = None, phone: str | None = None,
                   source: str = "manual") -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO customer_contacts (company_id, customer_ref, email, phone, source, updated_at)
               VALUES (%s, %s, %s, %s, %s, NOW())
               ON CONFLICT (company_id, customer_ref) DO UPDATE SET
                 email  = COALESCE(EXCLUDED.email, customer_contacts.email),
                 phone  = COALESCE(EXCLUDED.phone, customer_contacts.phone),
                 source = EXCLUDED.source, updated_at = NOW()""",
            (company_id, customer_ref, email or None, phone or None, source),
        )
    conn.commit()


def populate_from_zoho(conn, company_id: str) -> int:
    """Fill customer_contacts from Zoho contacts (email/phone we otherwise lack).
    Idempotent; only touches customers that have an email."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO customer_contacts (company_id, customer_ref, email, phone, source, updated_at)
               SELECT %s, contact_name, NULLIF(email, ''),
                      NULLIF(COALESCE(phone, mobile), ''), 'zoho', NOW()
               FROM zb_contacts
               WHERE company_id = %s
                 AND (contact_type IS NULL OR contact_type ILIKE 'customer')
                 AND contact_name IS NOT NULL AND COALESCE(email, '') <> ''
               ON CONFLICT (company_id, customer_ref) DO UPDATE SET
                 email  = COALESCE(EXCLUDED.email, customer_contacts.email),
                 source = 'zoho', updated_at = NOW()""",
            (company_id, company_id),
        )
        n = cur.rowcount
    conn.commit()
    return n


# ── email delivery ────────────────────────────────────────────────────────────
def email_provider() -> str | None:
    if os.getenv("RESEND_API_KEY"):
        return "resend"
    if os.getenv("SMTP_HOST"):
        return "smtp"
    return None


def _from_addr() -> str:
    return os.getenv("EMAIL_FROM", "BIDE <no-reply@bide.local>")


def send_email(to: str | None, subject: str, body: str) -> dict:
    """Deliver an email via the configured provider. Never raises — returns a
    dict {sent, provider?, to?, error?} so the caller records the outcome."""
    if not to:
        return {"sent": False, "error": "no recipient email"}
    prov = email_provider()
    if prov is None:
        return {"sent": False, "error": "email provider not configured"}
    try:
        if prov == "resend":
            import requests
            r = requests.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
                         "Content-Type": "application/json"},
                json={"from": _from_addr(), "to": [to], "subject": subject, "text": body},
                timeout=20,
            )
            if r.status_code // 100 == 2:
                rid = (r.json() or {}).get("id") if r.content else None
                return {"sent": True, "provider": "resend", "to": to, "id": rid}
            return {"sent": False, "provider": "resend", "error": f"HTTP {r.status_code}: {r.text[:200]}"}

        # SMTP
        host = os.environ["SMTP_HOST"]
        port = int(os.getenv("SMTP_PORT", "587"))
        user, pw = os.getenv("SMTP_USER"), os.getenv("SMTP_PASSWORD")
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = _from_addr(), to, subject
        msg.set_content(body)
        with smtplib.SMTP(host, port, timeout=20) as s:
            s.starttls(context=ssl.create_default_context())
            if user:
                s.login(user, pw or "")
            s.send_message(msg)
        return {"sent": True, "provider": "smtp", "to": to}
    except Exception as exc:  # noqa: BLE001 — delivery failure is data, not a crash
        logger.warning("send_email failed via %s: %s", prov, exc)
        return {"sent": False, "provider": prov, "error": str(exc)[:200]}
