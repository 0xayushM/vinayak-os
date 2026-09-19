"""
alerts.py
──────────
When background work fails, somebody hears about it — once.

Every failure path in the background already logged. That is not the same as
anyone knowing: a log line is read by the person who goes looking, and nobody
goes looking at a system that appears to work. The dashboard does not break
when a sync fails, it just stops changing, which is exactly the failure that
surfaces days later as "why are these numbers old?". An email to ALERT_EMAIL
closes that gap.

The other half is not crying wolf. A sync that fails hourly would otherwise be
twenty-four emails a day, and the second one teaches the reader to filter the
rest. So each CONDITION has a dedupe key ("sync_failed:kbrushes:sales_invoices")
and is emailed at most once per ALERT_COOLDOWN_HOURS while it persists. The
`alerts` table (migration 025) is that memory; if the database is the thing
that is down, a per-process memory stands in for it.

Two rules hold everywhere in this module:

  • raise_alert never raises. It is called from inside the jobs it watches, and
    an alert that breaks the job it was reporting on is worse than none.
  • the decisions — is this worth an alert, has this already been sent — are
    pure functions of their inputs, so they are tested without a database.

Env:
  ALERT_EMAIL             comma-separated recipients. Unset → alerts are logged
                          at ERROR and recorded, but not emailed.
  ALERT_COOLDOWN_HOURS    how long a persisting condition stays quiet (default 6)
  plus the email provider vars in notify.py (RESEND_API_KEY or SMTP_*).
"""
from __future__ import annotations

import logging
import os
import socket
import threading
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DEFAULT_COOLDOWN_HOURS = 6.0


# ── pure decisions ────────────────────────────────────────────────────────

def recipients(raw: str | None) -> list[str]:
    """ALERT_EMAIL → addresses. Blank entries and whitespace are dropped, and
    a duplicate address is only mailed once."""
    out: list[str] = []
    for part in (raw or "").replace(";", ",").split(","):
        addr = part.strip()
        if addr and "@" in addr and addr not in out:
            out.append(addr)
    return out


def cooldown_hours(raw: str | None) -> float:
    """A bad value falls back to the default rather than to zero: a typo in an
    env var must not turn a quiet alert into an hourly one."""
    try:
        v = float(raw) if raw not in (None, "") else DEFAULT_COOLDOWN_HOURS
    except (TypeError, ValueError):
        return DEFAULT_COOLDOWN_HOURS
    return v if v > 0 else DEFAULT_COOLDOWN_HOURS


def should_send(last_sent_at: datetime | None, now: datetime,
                cooldown: float) -> bool:
    """Email now, or has this condition already been reported recently?

    Only a SUCCESSFUL send starts the cooldown (callers restore last_sent_at
    when delivery fails), so a condition that could not be emailed is tried
    again the next time it recurs rather than going quiet unreported."""
    if last_sent_at is None:
        return True
    return now - last_sent_at >= timedelta(hours=cooldown)


def watcher_halted(consecutive_errors: int | None, max_errors: int) -> bool:
    """A watcher that has failed this many times in a row is no longer
    scheduled (runner.due excludes it). That is a silent stop unless said."""
    return consecutive_errors is not None and consecutive_errors >= max_errors


def brief_failure(result: dict) -> str | None:
    """Why a workspace's morning brief did not reach anyone, or None if it did
    (or if there was legitimately nothing to send).

    no_data is not a failure: a workspace with nothing synced has no brief.
    no_recipients IS: the brief exists and nobody will read it, which is the
    same outcome as a send that failed, only quieter."""
    if result.get("sent"):
        return None
    reason = result.get("reason")
    if reason == "no_data":
        return None
    if reason == "no_recipients":
        return "no recipients are set up for the brief"
    if result.get("error"):
        return f"the brief could not be built: {result['error']}"
    errors = sorted({str(r.get("error") or "unknown error")
                     for r in (result.get("results") or []) if not r.get("sent")})
    n = int(result.get("recipients") or 0)
    return (f"delivery failed for all {n} recipient{'s' if n != 1 else ''}"
            + (f": {'; '.join(errors)}" if errors else ""))


def compose(kind: str, subject: str, detail: str, *, company_id: str | None,
            cooldown: float, host: str | None = None) -> tuple[str, str]:
    """(subject, body) of the email. Plain text: it is read on a phone."""
    subj = f"[BIDE alert] {subject}"
    lines = [
        subject,
        "",
        detail.strip() if detail else "(no detail)",
        "",
        f"Kind:      {kind}",
        f"Workspace: {company_id or '(all)'}",
        f"Reported:  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
        + (f" by {host}" if host else ""),
        "",
        f"While this condition persists you will not be emailed about it again "
        f"for {cooldown:g} hours. The Sync page shows current worker health.",
    ]
    return subj, "\n".join(lines)


# ── delivery ──────────────────────────────────────────────────────────────

# Stand-in memory for when the alerts table cannot be reached — which is
# precisely when alerts are most likely to be firing.
_local_sent: dict[str, datetime] = {}
_local_lock = threading.Lock()


def _connect():
    import psycopg2
    from vinayak.config import DATABASE_URL
    return psycopg2.connect(DATABASE_URL, connect_timeout=10)


def raise_alert(kind: str, dedupe_key: str, subject: str, detail: str = "", *,
                company_id: str | None = None) -> dict:
    """Record a failing condition and email it unless it was emailed recently.

    Opens its own connection: the caller's is often in an aborted transaction,
    and an alert must not commit (or roll back) someone else's work. Never
    raises. Returns what happened, for tests and for the caller's log."""
    try:
        return _raise_alert(kind, dedupe_key, subject, detail, company_id)
    except Exception as exc:  # noqa: BLE001 — see module docstring
        logger.error("alert %s could not be processed: %s", dedupe_key, exc)
        return {"sent": False, "error": str(exc)}


def _raise_alert(kind, dedupe_key, subject, detail, company_id) -> dict:
    detail = (detail or "")[:4000]
    # Always in the log, whatever happens next: an alert with no email
    # configured must still be findable.
    logger.error("ALERT %s [%s] %s — %s", kind, dedupe_key, subject, detail[:500])

    now = datetime.now(timezone.utc)
    cooldown = cooldown_hours(os.getenv("ALERT_COOLDOWN_HOURS"))
    to = recipients(os.getenv("ALERT_EMAIL"))

    conn = None
    try:
        conn = _connect()
    except Exception as exc:  # noqa: BLE001
        logger.warning("alerts table unreachable, using process memory: %s", exc)
        conn = None

    try:
        previous = None
        if conn is not None:
            try:
                previous = _claim(conn, kind, dedupe_key, subject, detail, company_id)
            except Exception as exc:  # noqa: BLE001 — e.g. migration 025 not applied
                logger.warning("alerts table unusable, using process memory: %s", exc)
                conn.close()
                conn = None
        if conn is None:
            with _local_lock:
                previous = _local_sent.get(dedupe_key)

        if not should_send(previous, now, cooldown):
            if conn is not None:
                conn.commit()        # keep last_seen_at / times_seen, release the row
            return {"sent": False, "suppressed": True, "key": dedupe_key}

        # Claimed: mark as sent before sending, so a second process arriving
        # while the email is in flight sees it and stays quiet.
        _mark(conn, dedupe_key, now)

        error = None
        if not to:
            error = "ALERT_EMAIL is not set"
        else:
            try:
                from vinayak import notify
                subj, body = compose(kind, subject, detail, company_id=company_id,
                                     cooldown=cooldown, host=socket.gethostname())
                results = [notify.send_email(addr, subj, body) for addr in to]
                if not any(r.get("sent") for r in results):
                    error = "; ".join(sorted({str(r.get("error")) for r in results}))
            except Exception as exc:  # noqa: BLE001 — must still reach _unmark
                error = f"sending raised {type(exc).__name__}: {exc}"

        if error:
            logger.error("ALERT %s was not emailed: %s", dedupe_key, error)
            _unmark(conn, dedupe_key, previous, error)
            return {"sent": False, "key": dedupe_key, "error": error}
        return {"sent": True, "key": dedupe_key, "to": to}
    finally:
        if conn is not None:
            conn.close()


def _claim(conn, kind, key, subject, detail, company_id) -> datetime | None:
    """Upsert the condition and return when it was last emailed. The upsert
    holds the row lock until commit, so two processes cannot both read
    'never sent' — the second waits and reads the first one's mark."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO alerts (dedupe_key, kind, company_id, subject, detail)
               VALUES (%s,%s,%s,%s,%s)
               ON CONFLICT (dedupe_key) DO UPDATE
                  SET last_seen_at = NOW(), times_seen = alerts.times_seen + 1,
                      subject = EXCLUDED.subject, detail = EXCLUDED.detail
               RETURNING last_sent_at""",
            (key, kind, company_id, subject, detail))
        row = cur.fetchone()
    return row[0] if row else None


def _mark(conn, key: str, now: datetime) -> None:
    if conn is None:
        with _local_lock:
            _local_sent[key] = now
        return
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE alerts SET last_sent_at = %s, times_sent = times_sent + 1,
                      last_error = NULL
                WHERE dedupe_key = %s""", (now, key))
    conn.commit()


def _unmark(conn, key: str, previous: datetime | None, error: str) -> None:
    """Delivery failed: put the cooldown back where it was, so the next
    occurrence tries again instead of being suppressed as already reported."""
    if conn is None:
        with _local_lock:
            if previous is None:
                _local_sent.pop(key, None)
            else:
                _local_sent[key] = previous
        return
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE alerts SET last_sent_at = %s,
                      times_sent = GREATEST(times_sent - 1, 0), last_error = %s
                WHERE dedupe_key = %s""", (previous, error[:1000], key))
    conn.commit()


# ── the conditions ────────────────────────────────────────────────────────
# Thin wrappers so every call site uses the same key shape: one condition,
# one key, regardless of which code path noticed it.

def sync_failed(company_id: str, pipeline: str, error: str) -> dict:
    return raise_alert(
        "sync_failed", f"sync_failed:{company_id}:{pipeline}",
        f"Sync failing: {pipeline} for {company_id}",
        f"The {pipeline} sync for {company_id} failed. Existing data stays on "
        f"screen but will not update until this is fixed.\n\nError: {error}",
        company_id=company_id)


def canonical_failed(company_id: str, source: str, error: str) -> dict:
    return raise_alert(
        "canonical_failed", f"canonical_failed:{company_id}:{source}",
        f"Canonical rebuild failing: {source} for {company_id}",
        f"Raw {source} data synced, but rebuilding the canonical layer the "
        f"dashboard reads from failed — pages will show the previous figures."
        f"\n\nError: {error}",
        company_id=company_id)


def creds_failed(company_id: str, tool: str, error: str) -> dict:
    return raise_alert(
        "creds_failed", f"creds_failed:{company_id}:{tool}",
        f"Stored {tool} credentials unusable for {company_id}",
        f"The scheduled {tool} sync for {company_id} was skipped because its "
        f"stored credentials could not be read.\n\nError: {error}",
        company_id=company_id)


def watcher_halted_alert(company_id: str, key: str, errors: int, error: str) -> dict:
    return raise_alert(
        "watcher_halted", f"watcher_halted:{company_id}:{key}",
        f"Watcher halted: {key} for {company_id}",
        f"{key} failed {errors} times in a row and is no longer being run for "
        f"{company_id}. It stays halted until someone turns it back on from "
        f"the Business Brain page.\n\nLast error: {error}",
        company_id=company_id)


def brief_failed(company_id: str, reason: str) -> dict:
    return raise_alert(
        "brief_failed", f"brief_failed:{company_id}",
        f"Morning brief not delivered for {company_id}",
        f"This morning's brief for {company_id} reached nobody: {reason}.",
        company_id=company_id)


def job_error(job_id: str, error: str) -> dict:
    return raise_alert(
        "job_error", f"job_error:{job_id}",
        f"Background job crashed: {job_id}",
        f"The scheduled job {job_id} raised an exception it did not handle."
        f"\n\nError: {error}")
