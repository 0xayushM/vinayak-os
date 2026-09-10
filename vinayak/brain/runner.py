"""
brain/runner.py
────────────────
Runs one watcher, inside one episode.

Everything the brain does on its own happens through this function, so that
every pass leaves a row in brain_runs saying when it ran, how long it took,
what it found, and what broke if anything did. A background system without
that log is a system nobody can answer questions about, and "why did it chase
that customer on Tuesday?" is a question that gets asked.

Two safety rails, both mundane and both load-bearing:

  • a watcher that throws is caught, recorded, and counted. Three failures in
    a row disable it for that company rather than filling the log forever.
  • the run row is written even when the watcher fails, in its own
    transaction, so the record of a crash survives the crash.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone

from vinayak.brain.registry import Watcher, all_watchers, by_key

logger = logging.getLogger(__name__)

# After this many consecutive failures a watcher stops being scheduled for
# that company. It stays in the table with its error, waiting for a person.
MAX_CONSECUTIVE_ERRORS = 3


def ensure_registered(conn, company_id: str) -> int:
    """Give a company a row for every watcher it does not have yet, with the
    code's defaults. New watchers reach existing companies the same way."""
    n = 0
    with conn.cursor() as cur:
        for w in all_watchers():
            cur.execute(
                """INSERT INTO workflows (company_id, workflow_key, interval_minutes, config)
                   VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (company_id, w.key, w.interval_minutes, json.dumps(w.default_config)),
            )
            n += cur.rowcount or 0
    conn.commit()
    return n


def due(conn, company_id: str, *, now: datetime | None = None) -> list[str]:
    """Which watchers are due for this company, most overdue first."""
    now = now or datetime.now(timezone.utc)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT workflow_key, interval_minutes, last_run_at
                 FROM workflows
                WHERE company_id = %s AND enabled = TRUE
                  AND consecutive_errors < %s""",
            (company_id, MAX_CONSECUTIVE_ERRORS),
        )
        rows = cur.fetchall()
    known = by_key()
    out: list[tuple[float, str]] = []
    for key, interval, last in rows:
        if key not in known:                      # a watcher removed from the code
            continue
        if last is None:
            out.append((float("inf"), key))
            continue
        overdue_by = (now - last).total_seconds() / 60 - float(interval)
        if overdue_by >= 0:
            out.append((overdue_by, key))
    out.sort(key=lambda x: x[0], reverse=True)
    return [k for _, k in out]


def run(conn, company_id: str, key: str, *, trigger: str = "schedule") -> dict:
    """Run one watcher and record the episode. Never raises."""
    watcher = by_key().get(key)
    if watcher is None:
        raise KeyError(f"unknown workflow: {key}")

    config = _config_for(conn, company_id, key, watcher)
    run_id = _open_run(conn, company_id, key, trigger)
    started = time.monotonic()

    try:
        result = watcher.fn(conn, company_id, run_id=run_id, config=config) or {}
        conn.commit()
    except Exception as exc:  # noqa: BLE001 — a watcher must not take the worker down
        conn.rollback()
        logger.exception("watcher %s failed for %s", key, company_id)
        _close_run(conn, run_id, status="error", ms=_ms(started), error=str(exc)[:2000],
                   summary=f"{watcher.title} could not finish.")
        _record_failure(conn, company_id, key, str(exc)[:2000])
        return {"run_id": run_id, "status": "error", "error": str(exc)}

    events = int(result.get("events_emitted", 0))
    actions = int(result.get("actions_proposed", 0))
    summary = result.get("summary") or _summarise(watcher, events, actions, result)
    _close_run(conn, run_id, status="ok", ms=_ms(started), summary=summary,
               events=events, actions=actions, detail=result)
    _record_success(conn, company_id, key)
    return {"run_id": run_id, "status": "ok", "summary": summary,
            "events_emitted": events, "actions_proposed": actions, "detail": result}


def run_due(conn, company_id: str, *, now: datetime | None = None,
            max_watchers: int = 6) -> list[dict]:
    """One worker tick for one company."""
    ensure_registered(conn, company_id)
    return [run(conn, company_id, key) for key in due(conn, company_id, now=now)[:max_watchers]]


# ── the run log ───────────────────────────────────────────────────────────

def _open_run(conn, company_id: str, key: str, trigger: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO brain_runs (company_id, workflow_key, trigger)
               VALUES (%s,%s,%s) RETURNING id""", (company_id, key, trigger))
        rid = int(cur.fetchone()[0])
    conn.commit()
    return rid


def _close_run(conn, run_id: int, *, status: str, ms: int, summary: str | None = None,
               events: int = 0, actions: int = 0, detail: dict | None = None,
               error: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE brain_runs
                  SET finished_at = NOW(), duration_ms = %s, status = %s,
                      events_emitted = %s, actions_proposed = %s,
                      summary = %s, detail = %s, error = %s
                WHERE id = %s""",
            (ms, status, events, actions, summary,
             json.dumps(detail or {}, default=str), error, run_id))
    conn.commit()


def _record_success(conn, company_id: str, key: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE workflows SET last_run_at = NOW(), last_status = 'ok',
                      last_error = NULL, consecutive_errors = 0
                WHERE company_id = %s AND workflow_key = %s""", (company_id, key))
    conn.commit()


def _record_failure(conn, company_id: str, key: str, error: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE workflows
                  SET last_run_at = NOW(), last_status = 'error', last_error = %s,
                      consecutive_errors = consecutive_errors + 1
                WHERE company_id = %s AND workflow_key = %s""", (error, company_id, key))
    conn.commit()


def _config_for(conn, company_id: str, key: str, watcher: Watcher) -> dict:
    """Code defaults, overridden by whatever the company's row says."""
    with conn.cursor() as cur:
        cur.execute("SELECT config FROM workflows WHERE company_id=%s AND workflow_key=%s",
                    (company_id, key))
        row = cur.fetchone()
    return {**watcher.default_config, **((row[0] if row else None) or {})}


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _summarise(watcher: Watcher, events: int, actions: int, result: dict) -> str:
    """One plain sentence, built from the counts — never written by a model."""
    if suggestions := int(result.get("suggested", 0)):
        return f"{suggestions} experiment{'s' if suggestions > 1 else ''} suggested."
    if closed := int(result.get("closed", 0)):
        return f"{closed} experiment{'s' if closed > 1 else ''} closed with an outcome."
    parts = []
    if events:
        parts.append(f"{events} new event{'s' if events > 1 else ''}")
    if actions:
        parts.append(f"{actions} proposal{'s' if actions > 1 else ''} for approval")
    if not parts:
        return "Nothing new."
    return watcher.title + ": " + " and ".join(parts) + "."


def recent_runs(conn, company_id: str, limit: int = 40) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, workflow_key, trigger, started_at, finished_at, duration_ms,
                      status, events_emitted, actions_proposed, summary, error
                 FROM brain_runs WHERE company_id = %s
                ORDER BY started_at DESC LIMIT %s""", (company_id, limit))
        rows = cur.fetchall()
    titles = {w.key: w.title for w in all_watchers()}
    return [{"id": int(r[0]), "workflow_key": r[1], "title": titles.get(r[1], r[1]),
             "trigger": r[2],
             "started_at": r[3].isoformat() if r[3] else None,
             "finished_at": r[4].isoformat() if r[4] else None,
             "duration_ms": r[5], "status": r[6],
             "events_emitted": int(r[7] or 0), "actions_proposed": int(r[8] or 0),
             "summary": r[9], "error": r[10]} for r in rows]


def workflow_status(conn, company_id: str) -> list[dict]:
    """The registry as the page shows it: what exists, what it does, when it
    last ran and when it runs next."""
    ensure_registered(conn, company_id)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT workflow_key, enabled, interval_minutes, last_run_at,
                      last_status, last_error, consecutive_errors
                 FROM workflows WHERE company_id = %s""", (company_id,))
        rows = {r[0]: r for r in cur.fetchall()}
    out = []
    for w in all_watchers():
        r = rows.get(w.key)
        last = r[3] if r else None
        interval = int(r[2]) if r else w.interval_minutes
        out.append({
            "key": w.key, "title": w.title, "what_it_does": w.what_it_does,
            "enabled": bool(r[1]) if r else True,
            "interval_minutes": interval,
            "last_run_at": last.isoformat() if last else None,
            "next_run_at": (last + timedelta(minutes=interval)).isoformat() if last else None,
            "last_status": r[4] if r else None,
            "last_error": r[5] if r else None,
            "halted": bool(r and int(r[6] or 0) >= MAX_CONSECUTIVE_ERRORS),
        })
    return out


def set_enabled(conn, company_id: str, key: str, enabled: bool) -> None:
    """Turning a watcher back on also clears its error count — otherwise a
    halted watcher would stay halted after someone had fixed the cause."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE workflows SET enabled = %s,
                      consecutive_errors = CASE WHEN %s THEN 0 ELSE consecutive_errors END
                WHERE company_id = %s AND workflow_key = %s""",
            (enabled, enabled, company_id, key))
    conn.commit()
