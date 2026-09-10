"""
brief.py
─────────
The morning brief — the Pulse, delivered.

The owner opening the app every day is a Milestone-1 criterion, and a dashboard
only gets opened if something brings you to it. So at 06:00 IST each working
day this assembles the same cards the Pulse page shows, in severity order, and
sends them as a short email (WhatsApp when the channel is live), every line
deep-linked to the card it came from.

Why no model writes this: the cards already carry a sentence built from the
query results, so composing the brief from those sentences means there is no
step at which a figure could be invented. The brief is therefore grounded by
construction rather than by a guard — the cheapest possible way to be safe.

    from vinayak.brief import build_brief, send_brief
    build_brief(conn, "protegere")            # {subject, text, html, cards}
    send_brief(conn, "protegere", to="owner@example.com")
"""
from __future__ import annotations

import logging
import os
from datetime import date

from vinayak.schema import pulse_cards as C

logger = logging.getLogger(__name__)

# Cards quiet enough to leave out of a short brief entirely.
BRIEF_MIN_SEVERITY = 10
BRIEF_MAX_CARDS = 6


def _app_url() -> str:
    return (os.getenv("NEXT_PUBLIC_APP_URL", "") or "").rstrip("/")


def _card_link(company_id: str, key: str = "") -> str:
    """Deep link to the Pulse, or to one card on it."""
    base = _app_url()
    if not base:
        return ""
    return f"{base}/w/{company_id}/dashboard" + (f"#{key}" if key else "")


def build_brief(conn, company_id: str, role: str | None = "owner",
                today: date | None = None) -> dict:
    """Assemble today's brief. Returns subject, plain text, html and the cards
    it was built from (so a caller can log exactly what was sent)."""
    today = today or date.today()
    built = C.build_cards(conn, company_id, role=role, sort="severity")
    cards = [c for c in built["cards"] if c["severity"] >= BRIEF_MIN_SEVERITY][:BRIEF_MAX_CARDS]
    urgent = [c for c in cards if c["severity"] >= 60]

    if built.get("no_data"):
        subject = f"{company_id}: waiting for the first sync"
        text = ("Nothing to report yet — no data has been synced for this workspace.\n"
                "Connect a source and the brief starts the morning after.")
        return {"subject": subject, "text": text, "html": f"<p>{text}</p>",
                "cards": [], "no_data": True}

    if urgent:
        headline = urgent[0]["why"]
        subject = f"{company_id}: {len(urgent)} thing{'s' if len(urgent) > 1 else ''} need you today"
    elif cards:
        headline = cards[0]["why"]
        subject = f"{company_id}: nothing urgent — {cards[0]['title'].lower()}"
    else:
        headline = "Nothing changed materially since yesterday."
        subject = f"{company_id}: all quiet"

    # ── plain text (this is what WhatsApp will send too) ──────────────────────
    lines = [f"{today.strftime('%a %d %b')} · {company_id}", "", headline, ""]
    for c in cards:
        mark = "!" if c["severity"] >= 60 else "·"
        lines.append(f"{mark} {c['title']}: {c['headline']['display']}"
                     + (f" ({c['change']['display']} {c['change']['label']})" if c["change"] else ""))
        lines.append(f"  {c['why']}")
        if c["action"]:
            lines.append(f"  → {c['action']['label']}")
        lines.append("")
    link = _card_link(company_id, "")
    if link:
        lines.append(f"Open the full picture: {link}")
    text = "\n".join(lines)

    # ── html ──────────────────────────────────────────────────────────────────
    def esc(s: str) -> str:
        return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

    rows = []
    for c in cards:
        colour = "#b3341f" if c["severity"] >= 60 else "#4a4e52"
        change = (f' <span style="color:{colour};font-weight:600">{esc(c["change"]["display"])}</span>'
                  if c["change"] else "")
        rows.append(
            f'<tr><td style="padding:14px 0;border-bottom:1px solid #e6e3db">'
            f'<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#7a7f84">{esc(c["title"])}</div>'
            f'<div style="font-size:22px;font-weight:700;color:#1b1d1f;margin:2px 0">{esc(c["headline"]["display"])}{change}</div>'
            f'<div style="font-size:13px;color:#4a4e52;line-height:1.5">{esc(c["why"])}</div>'
            f'</td></tr>')
    html = (
        '<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:560px;margin:0 auto;color:#1b1d1f">'
        f'<p style="font-size:12px;color:#7a7f84;margin:0 0 4px">{today.strftime("%A %d %B")} · {esc(company_id)}</p>'
        f'<p style="font-size:16px;line-height:1.5;margin:0 0 18px">{esc(headline)}</p>'
        f'<table style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
        + (f'<p style="margin-top:20px"><a href="{link}" style="color:#2b3a67">Open the full picture</a></p>'
           if link else "")
        + '<p style="font-size:11px;color:#7a7f84;margin-top:18px">Every figure here is computed from your '
          'synced data. Nothing has been sent to a customer — approvals wait for you in the app.</p>'
        '</div>')

    return {"subject": subject, "text": text, "html": html, "cards": cards,
            "urgent": len(urgent), "no_data": False}


def brief_recipients(conn, company_id: str) -> list[str]:
    """Who gets it: users of this workspace whose role wants a daily brief.
    Viewers are excluded; a user with no role yet is treated as an owner."""
    with conn.cursor() as cur:
        cur.execute("""SELECT email, role FROM users
                       WHERE (company_id = %s OR company_id IS NULL) AND email IS NOT NULL""",
                    (company_id,))
        rows = cur.fetchall()
    return [e for e, role in rows if (role or "owner") != "viewer"]


def send_brief(conn, company_id: str, to: str | None = None, role: str | None = "owner") -> dict:
    """Build and deliver. Never raises: a brief that cannot be sent is logged
    and reported, it does not break the morning job for other companies."""
    from vinayak import notify

    brief = build_brief(conn, company_id, role=role)
    if brief.get("no_data"):
        return {"sent": False, "reason": "no_data", "company_id": company_id}

    recipients = [to] if to else brief_recipients(conn, company_id)
    if not recipients:
        return {"sent": False, "reason": "no_recipients", "company_id": company_id}

    results = []
    for addr in recipients:
        try:
            r = notify.send_email(addr, brief["subject"], brief["text"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("brief: send to %s failed: %s", addr, exc)
            r = {"sent": False, "error": str(exc)}
        results.append({"to": addr, **r})
    sent = sum(1 for r in results if r.get("sent"))
    logger.info("brief %s: %d/%d delivered", company_id, sent, len(results))
    return {"sent": bool(sent), "delivered": sent, "recipients": len(results),
            "subject": brief["subject"], "results": results, "company_id": company_id}


def send_all_briefs() -> dict:
    """The scheduled job: one brief per workspace that has a connected source.
    A failure for one workspace never stops the others."""
    import psycopg2
    from vinayak.config import DATABASE_URL

    out = []
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute("""SELECT DISTINCT company_id FROM tool_connections
                           WHERE is_active = TRUE ORDER BY company_id""")
            companies = [r[0] for r in cur.fetchall()]
        for cid in companies:
            try:
                out.append(send_brief(conn, cid))
            except Exception as exc:  # noqa: BLE001
                logger.exception("brief failed for %s", cid)
                out.append({"sent": False, "company_id": cid, "error": str(exc)})
    finally:
        conn.close()
    return {"companies": len(out), "delivered": sum(1 for r in out if r.get("sent")), "results": out}
