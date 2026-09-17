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

Two things ride along with the cards:

  • experiments waiting for a decision. Milestone 1 needs 30 experiments with
    outcomes, and the Strategy watcher already suggests them; what is missing
    is a person saying yes. The brief is the one thing he reads daily, so the
    nudge lives here — built from rows in the experiments table, never from a
    model, the same as the cards.

  • a delivery log. "The brief arrived every working day for the preceding 30
    days" is a month-3 demo criterion, so every attempt is written to
    brief_deliveries and `delivery_days` answers the question from there.

    from vinayak.brief import build_brief, send_brief, delivery_days
    build_brief(conn, "protegere")            # {subject, text, html, cards, ...}
    send_brief(conn, "protegere", to="owner@example.com")
    delivery_days(conn, "protegere", "owner@example.com", days=30)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from vinayak.schema import pulse_cards as C

logger = logging.getLogger(__name__)

# Cards quiet enough to leave out of a short brief entirely.
BRIEF_MIN_SEVERITY = 10
BRIEF_MAX_CARDS = 6

# The brief is for the owner's working day and the scheduler fires at 06:00
# IST — so "today" is the IST date, whatever the server's clock says.
_IST = ZoneInfo("Asia/Kolkata")

# Monday–Saturday. The scheduler sends every morning, Sunday included (a
# Sunday brief costs nothing), but the evidence only OWES a brief on the days
# the factory works: a six-day week is the norm for these businesses, and a
# quiet Sunday must not break a 30-day record.
WORKING_WEEKDAYS = frozenset(range(6))

# Experiments: how long a suggestion may sit before the brief mentions it on a
# day other than Monday, and how many titles the Monday note names.
WAIT_NUDGE_DAYS = 3
EXPERIMENT_TITLES = 3


def today_ist(now: datetime | None = None) -> date:
    return (now or datetime.now(_IST)).astimezone(_IST).date()


def _app_url() -> str:
    return (os.getenv("NEXT_PUBLIC_APP_URL", "") or "").rstrip("/")


def _card_link(company_id: str, key: str = "") -> str:
    """Deep link to the Pulse, or to one card on it."""
    base = _app_url()
    if not base:
        return ""
    return f"{base}/w/{company_id}/dashboard" + (f"#{key}" if key else "")


def _experiments_link(company_id: str) -> str:
    base = _app_url()
    return f"{base}/w/{company_id}/dashboard/experiments" if base else ""


def _as_date(v) -> date | None:
    """experiments._row hands back ISO strings; accept real dates too."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)).date()
    except ValueError:
        return None


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


# ── experiments waiting for a decision (pure) ────────────────────────────────
def experiments_section(proposed: list[dict], running: list[dict], today: date,
                        company_id: str) -> dict | None:
    """What the brief says about experiments today, or None to say nothing.

    The visibility rule, stated once so it can be argued with in a test:

      • Monday — the full note: how many suggestions are waiting, the
        longest-waiting few by title, and running experiments whose window
        ends this week. The Strategy watcher files weekly, so Monday is the
        natural morning to decide the week's experiments.
      • Any other day — ONE line, and only once a suggestion has waited longer
        than WAIT_NUDGE_DAYS. Nothing gets accepted by being mentioned once a
        week and forgotten, but a list repeated every morning is one people
        learn to scroll past; a single line with a count is the compromise.
        A running experiment is mentioned on the morning its window ends.

    Titles are listed oldest first: a queue is cleared from the front, and
    rejecting a stale suggestion helps as much as accepting a fresh one.
    """
    is_monday = today.weekday() == 0
    lines: list[str] = []
    titles: list[str] = []

    waiting = sorted(proposed, key=lambda e: _as_date(e.get("created_at")) or today)
    n = len(waiting)
    oldest_wait = 0
    if waiting:
        oldest_wait = max(0, (today - (_as_date(waiting[0].get("created_at")) or today)).days)
    if n and is_monday:
        lines.append(f"{_plural(n, 'suggested experiment')} waiting for a decision"
                     + (f" (oldest {_plural(oldest_wait, 'day')})" if oldest_wait else "") + ".")
        titles = [e["title"] for e in waiting[:EXPERIMENT_TITLES]]
    elif n and oldest_wait > WAIT_NUDGE_DAYS:
        lines.append(f"{_plural(n, 'suggested experiment')} waiting for a decision, "
                     f"the oldest for {_plural(oldest_wait, 'day')}.")

    week_end = today + timedelta(days=6 - today.weekday())   # Sunday
    ending = []
    for e in running:
        end = _as_date(e.get("ends_at"))
        if end is not None and ((is_monday and today <= end <= week_end) or end == today):
            ending.append((end, e["title"]))
    ending.sort()
    if ending:
        named = ", ".join(f"{t} ({'today' if d == today else d.strftime('%a')})"
                          for d, t in ending)
        when = "today" if all(d == today for d, _ in ending) else "this week"
        verb = "ends" if len(ending) == 1 else "end"
        lines.append(f"{_plural(len(ending), 'running experiment')} {verb} {when}: {named}.")

    if not lines:
        return None
    return {"lines": lines, "titles": titles, "proposed": n,
            "oldest_wait_days": oldest_wait, "ending": len(ending),
            "link": _experiments_link(company_id)}


def _read_experiments(conn, company_id: str) -> tuple[list[dict], list[dict]]:
    """The two reads the section needs. A failure costs the section, never the
    brief — and the transaction is rolled back so the delivery log written
    later on the same connection is not lost along with it."""
    from vinayak import experiments as X
    try:
        return (X.list_for(conn, company_id, status="proposed"),
                X.list_for(conn, company_id, status="running"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("brief: experiments read failed for %s: %s", company_id, exc)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return [], []


def build_brief(conn, company_id: str, role: str | None = "owner",
                today: date | None = None) -> dict:
    """Assemble today's brief. Returns subject, plain text, html and the cards
    it was built from (so a caller can log exactly what was sent)."""
    today = today or today_ist()
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

    # Experiments come after the cards: they are a decision to make this week,
    # not a figure that moved overnight, and must never push a card out.
    proposed, running = _read_experiments(conn, company_id)
    exp = experiments_section(proposed, running, today, company_id)

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
    if exp:
        lines.append("Experiments")
        lines.extend(f"  {l}" for l in exp["lines"])
        lines.extend(f"  · {t}" for t in exp["titles"])
        if exp["link"]:
            lines.append(f"  → Accept or reject: {exp['link']}")
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
    exp_html = ""
    if exp:
        exp_html = (
            '<div style="margin-top:18px;padding:12px 14px;background:#f5f3ee;border-radius:6px">'
            '<div style="font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#7a7f84">Experiments</div>'
            + "".join(f'<div style="font-size:13px;color:#1b1d1f;line-height:1.5;margin-top:4px">{esc(l)}</div>'
                      for l in exp["lines"])
            + (('<ul style="margin:6px 0 0;padding-left:18px;font-size:13px;color:#4a4e52">'
                + "".join(f"<li>{esc(t)}</li>" for t in exp["titles"]) + "</ul>")
               if exp["titles"] else "")
            + (f'<div style="margin-top:8px;font-size:13px"><a href="{esc(exp["link"])}" '
               'style="color:#2b3a67">Accept or reject them</a></div>' if exp["link"] else "")
            + '</div>')
    html = (
        '<div style="font-family:-apple-system,Segoe UI,sans-serif;max-width:560px;margin:0 auto;color:#1b1d1f">'
        f'<p style="font-size:12px;color:#7a7f84;margin:0 0 4px">{today.strftime("%A %d %B")} · {esc(company_id)}</p>'
        f'<p style="font-size:16px;line-height:1.5;margin:0 0 18px">{esc(headline)}</p>'
        f'<table style="width:100%;border-collapse:collapse">{"".join(rows)}</table>'
        + exp_html
        + (f'<p style="margin-top:20px"><a href="{link}" style="color:#2b3a67">Open the full picture</a></p>'
           if link else "")
        + '<p style="font-size:11px;color:#7a7f84;margin-top:18px">Every figure here is computed from your '
          'synced data. Nothing has been sent to a customer — approvals wait for you in the app.</p>'
        '</div>')

    return {"subject": subject, "text": text, "html": html, "cards": cards,
            "urgent": len(urgent), "experiments": exp, "no_data": False}


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

    today = today_ist()
    brief = build_brief(conn, company_id, role=role, today=today)
    if brief.get("no_data"):
        return {"sent": False, "reason": "no_data", "company_id": company_id}

    recipients = [to] if to else brief_recipients(conn, company_id)
    if not recipients:
        return {"sent": False, "reason": "no_recipients", "company_id": company_id}

    results = []
    for addr in recipients:
        try:
            r = notify.send_email(addr, brief["subject"], brief["text"], html=brief["html"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("brief: send to %s failed: %s", addr, exc)
            r = {"sent": False, "error": str(exc)}
        log_delivery(conn, company_id, addr, brief, r, today)
        results.append({"to": addr, **r})
    sent = sum(1 for r in results if r.get("sent"))
    logger.info("brief %s: %d/%d delivered", company_id, sent, len(results))
    return {"sent": bool(sent), "delivered": sent, "recipients": len(results),
            "subject": brief["subject"], "results": results, "company_id": company_id}


# ── the delivery log: the brief as evidence ──────────────────────────────────
def log_delivery(conn, company_id: str, recipient: str, brief: dict, result: dict,
                 sent_on: date) -> bool:
    """Record one attempt, delivered or not. Never raises: the log is evidence
    ABOUT the send, and a missing table must not stop the next recipient's
    brief. Returns whether the row was written."""
    error = result.get("error")
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO brief_deliveries
                     (company_id, recipient, sent_on, delivered, provider, error,
                      subject, card_keys, urgent)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (company_id, (recipient or "").strip().lower(), sent_on,
                 bool(result.get("sent")), result.get("provider"),
                 str(error)[:500] if error else None,
                 brief.get("subject"),
                 json.dumps([c.get("key") for c in brief.get("cards") or []]),
                 int(brief.get("urgent") or 0)),
            )
        conn.commit()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("brief: delivery log failed for %s/%s: %s", company_id, recipient, exc)
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        return False


def is_working_day(d: date) -> bool:
    return d.weekday() in WORKING_WEEKDAYS


def delivery_summary(delivered_on: list[date], today: date, days: int = 30) -> dict:
    """Pure: did the brief arrive on every working day of the last `days` days?

    The window is the `days` calendar days ending today. Today is owed only
    once it has been delivered — a check run at 05:00 must not call the
    morning a miss before the 06:00 job has had its chance. A delivery on a
    non-working day is fine but is not counted, so a Sunday brief cannot paper
    over a missed Tuesday.
    """
    start = today - timedelta(days=days - 1)
    got = {d for d in delivered_on if start <= d <= today}
    expected = [d for d in (start + timedelta(days=i) for i in range(days))
                if is_working_day(d) and (d < today or d in got)]
    missed = [d for d in expected if d not in got]
    return {
        "window_start": start.isoformat(), "window_end": today.isoformat(), "days": days,
        "expected_working_days": len(expected),
        "delivered_working_days": len(expected) - len(missed),
        "missed": [d.isoformat() for d in missed],
        "last_delivered": max(got).isoformat() if got else None,
        "every_working_day": bool(expected) and not missed,
    }


def delivery_days(conn, company_id: str, recipient: str, days: int = 30,
                  today: date | None = None) -> dict:
    """The month-3 readiness question for one person: delivered working days
    against expected working days over the last `days` days."""
    today = today or today_ist()
    who = (recipient or "").strip().lower()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT sent_on FROM brief_deliveries
               WHERE company_id = %s AND recipient = %s AND delivered
                 AND sent_on BETWEEN %s AND %s""",
            (company_id, who, today - timedelta(days=days - 1), today),
        )
        got = [r[0] for r in cur.fetchall()]
    out = delivery_summary(got, today, days)
    out.update({"company_id": company_id, "recipient": who})
    return out


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
