"""
api/routes/brain.py
────────────────────
What the brain has been doing while nobody was watching.

  GET  /dashboard/brain              watchers, recent runs, recent events, counts
  GET  /dashboard/brain/runs         the episodic log
  GET  /dashboard/brain/events       the event feed
  PUT  /dashboard/brain/workflows/{key}   enable / disable / retune a watcher
  POST /dashboard/brain/run/{key}    run one watcher now (manual trigger)

This page exists because a background system that cannot be inspected is a
background system nobody trusts. Everything here is a read of brain_runs,
events and workflows — there is no separate telemetry to fall out of step
with what actually ran.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from vinayak.api.deps import get_db as _conn, get_current_user, require_workspace, TokenPayload
from vinayak.brain import bus, runner
from vinayak.brain.registry import by_key

logger = logging.getLogger(__name__)
router = APIRouter()


def _counts(conn, company_id: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT COUNT(*) FILTER (WHERE processed_at IS NULL),
                      COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days')
                 FROM events WHERE company_id = %s""", (company_id,))
        pending_events, events_week = cur.fetchone()
        cur.execute(
            """SELECT COUNT(*) FILTER (WHERE started_at > NOW() - INTERVAL '7 days'),
                      COUNT(*) FILTER (WHERE status = 'error'
                                        AND started_at > NOW() - INTERVAL '7 days'),
                      COALESCE(SUM(actions_proposed) FILTER (
                          WHERE started_at > NOW() - INTERVAL '7 days'), 0)
                 FROM brain_runs WHERE company_id = %s""", (company_id,))
        runs_week, errors_week, proposed_week = cur.fetchone()
        cur.execute(
            """SELECT COUNT(*) FROM actions
                WHERE company_id = %s AND status = 'proposed'
                  AND proposed_by = 'agent'""", (company_id,))
        awaiting = cur.fetchone()[0]
    return {"pending_events": int(pending_events or 0),
            "events_this_week": int(events_week or 0),
            "runs_this_week": int(runs_week or 0),
            "errors_this_week": int(errors_week or 0),
            "proposals_this_week": int(proposed_week or 0),
            "awaiting_approval": int(awaiting or 0)}


@router.get("/brain")
def brain(company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"workflows": runner.workflow_status(conn, company_id),
                "runs": runner.recent_runs(conn, company_id, limit=25),
                "events": bus.recent(conn, company_id, limit=25),
                "counts": _counts(conn, company_id)}
    finally:
        conn.close()


@router.get("/brain/runs")
def brain_runs(limit: int = Query(default=50, le=200),
               company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"runs": runner.recent_runs(conn, company_id, limit=limit)}
    finally:
        conn.close()


@router.get("/brain/events")
def brain_events(limit: int = Query(default=50, le=200),
                 company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"events": bus.recent(conn, company_id, limit=limit)}
    finally:
        conn.close()


@router.put("/brain/workflows/{key}")
def update_workflow(key: str, body: dict = Body(...),
                    company_id: str = Depends(require_workspace),
                    user: TokenPayload = Depends(get_current_user)):
    """Turn a watcher off, or change how often it runs and what it treats as
    worth an event. Thresholds are per-company on purpose: 'a large invoice'
    means something different in each of the group's businesses."""
    if key not in by_key():
        raise HTTPException(404, f"unknown watcher: {key}")
    conn = _conn()
    try:
        runner.ensure_registered(conn, company_id)
        if "enabled" in body:
            runner.set_enabled(conn, company_id, key, bool(body["enabled"]))
        sets, params = [], []
        if "interval_minutes" in body:
            minutes = int(body["interval_minutes"])
            if not 5 <= minutes <= 60 * 24 * 30:
                raise HTTPException(400, "interval_minutes must be between 5 and 43200")
            sets.append("interval_minutes = %s")
            params.append(minutes)
        if "config" in body:
            import json
            if not isinstance(body["config"], dict):
                raise HTTPException(400, "config must be an object")
            sets.append("config = %s")
            params.append(json.dumps(body["config"]))
        if sets:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE workflows SET {', '.join(sets)} "
                    "WHERE company_id = %s AND workflow_key = %s",
                    (*params, company_id, key))
            conn.commit()
        logger.info("brain: %s changed watcher %s for %s", user.sub, key, company_id)
        return {"workflows": runner.workflow_status(conn, company_id)}
    finally:
        conn.close()


@router.post("/brain/run/{key}")
def run_now(key: str, company_id: str = Depends(require_workspace)):
    """Run one watcher immediately. Useful on the day a company is onboarded,
    when waiting three hours to see whether anything works is not an option."""
    if key not in by_key():
        raise HTTPException(404, f"unknown watcher: {key}")
    conn = _conn()
    try:
        runner.ensure_registered(conn, company_id)
        result = runner.run(conn, company_id, key, trigger="manual")
        return {**result, "runs": runner.recent_runs(conn, company_id, limit=10)}
    finally:
        conn.close()
