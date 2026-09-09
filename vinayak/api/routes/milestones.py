"""
api/routes/milestones.py
─────────────────────────
The evidence surface for the contractual milestones (docs/reference/MILESTONES.md):

  GET  /dashboard/usage/me                — my active days and qualifying-week runs
  GET  /dashboard/usage/users             — everyone seen in this workspace (owner/admin)
  GET  /dashboard/experiments             — list (optionally by status)
  POST /dashboard/experiments             — create (manual or ai_suggested)
  GET  /dashboard/experiments/counts      — the Milestone-1 numbers
  PATCH/dashboard/experiments/{id}        — update fields / transition status
  GET  /dashboard/incidents · POST · PATCH
  GET  /dashboard/milestones              — the board: every M1 criterion with live numbers
  GET/PUT /dashboard/milestones/settings  — start date, the tracked user

Everything is scoped to the workspace like every other route. The board and
the users list are limited to owner/admin roles.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from vinayak import experiments as X
from vinayak import usage as U
from vinayak.api.deps import get_db as _conn, get_current_user, require_workspace, TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter()

MANAGER_ROLES = ("owner", "admin")


# ── helpers ───────────────────────────────────────────────────────────────────
def user_record(conn, email: str) -> dict:
    """The users row as the app sees it (role + permissions + layout)."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT email, company_id, role, may_approve_messages, may_approve_money,
                      pinned_cards, display_name
               FROM users WHERE LOWER(email) = LOWER(%s)""", (email,))
        r = cur.fetchone()
    if not r:
        return {"email": email, "role": None, "may_approve_messages": False,
                "may_approve_money": False, "pinned_cards": None, "display_name": None}
    return {"email": r[0], "company_id": r[1], "role": r[2],
            "may_approve_messages": bool(r[3]), "may_approve_money": bool(r[4]),
            "pinned_cards": r[5], "display_name": r[6]}


def _require_manager(conn, user: TokenPayload) -> dict:
    rec = user_record(conn, user.sub)
    if rec.get("role") not in MANAGER_ROLES:
        raise HTTPException(status_code=403, detail="Owner or admin role required")
    return rec


def _setting(conn, key: str, default: str = "") -> str:
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM platform_settings WHERE key = %s", (key,))
        r = cur.fetchone()
    return r[0] if r else default


def _set_setting(conn, key: str, value: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO platform_settings (key, value) VALUES (%s, %s)
               ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()""",
            (key, value))
    conn.commit()


# ── usage ─────────────────────────────────────────────────────────────────────
@router.get("/usage/me")
def usage_me(window_days: int = Query(default=120, ge=7, le=400),
             company_id: str = Depends(require_workspace),
             user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        return U.stats(conn, user.sub, window_days=window_days)
    finally:
        conn.close()


@router.get("/usage/users")
def usage_users(window_days: int = Query(default=120, ge=7, le=400),
                company_id: str = Depends(require_workspace),
                user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        _require_manager(conn, user)
        return {"users": U.users_seen(conn, company_id, window_days)}
    finally:
        conn.close()


# ── experiments ───────────────────────────────────────────────────────────────
class ExperimentIn(BaseModel):
    title: str
    hypothesis: str | None = None
    source: str = "manual"
    metric: str | None = None
    baseline: float | None = None
    target: float | None = None
    action_refs: list | None = None
    evidence: dict | None = None
    started_at: str | None = None
    ends_at: str | None = None
    status: str = "proposed"


class ExperimentPatch(BaseModel):
    title: str | None = None
    hypothesis: str | None = None
    metric: str | None = None
    baseline: float | None = None
    target: float | None = None
    result: float | None = None
    outcome: str | None = None
    outcome_notes: str | None = None
    action_refs: list | None = None
    evidence: dict | None = None
    started_at: str | None = None
    ends_at: str | None = None
    status: str | None = None


@router.get("/experiments")
def experiments_list(status: str | None = Query(default=None),
                     company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"experiments": X.list_for(conn, company_id, status=status),
                "counts": X.counts(conn, company_id)}
    finally:
        conn.close()


@router.get("/experiments/counts")
def experiments_counts(company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return X.counts(conn, company_id)
    finally:
        conn.close()


@router.post("/experiments")
def experiments_create(body: ExperimentIn, company_id: str = Depends(require_workspace),
                       user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        try:
            exp = X.create(conn, company_id, proposed_by=user.sub,
                           **body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"experiment": exp}
    finally:
        conn.close()


@router.patch("/experiments/{experiment_id}")
def experiments_update(experiment_id: str, body: ExperimentPatch,
                       company_id: str = Depends(require_workspace),
                       user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        try:
            exp = X.update(conn, company_id, experiment_id,
                           body.model_dump(exclude_none=True), by=user.sub)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if exp is None:
            raise HTTPException(status_code=404, detail="Experiment not found")
        return {"experiment": exp}
    finally:
        conn.close()


# ── incidents ─────────────────────────────────────────────────────────────────
class IncidentIn(BaseModel):
    severity: str          # critical | major | minor
    title: str
    detail: str | None = None
    started_at: str | None = None


class IncidentPatch(BaseModel):
    resolved: bool | None = None
    detail: str | None = None
    severity: str | None = None


_SEVERITIES = ("critical", "major", "minor")


def _incident_rows(conn, company_id: str, limit: int = 100) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, company_id, severity, title, detail, started_at, resolved_at, reported_by
               FROM incidents WHERE company_id = %s OR company_id IS NULL
               ORDER BY started_at DESC LIMIT %s""", (company_id, limit))
        rows = cur.fetchall()
    return [{"id": str(r[0]), "company_id": r[1], "severity": r[2], "title": r[3], "detail": r[4],
             "started_at": r[5].isoformat() if r[5] else None,
             "resolved_at": r[6].isoformat() if r[6] else None, "reported_by": r[7]} for r in rows]


@router.get("/incidents")
def incidents_list(company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"incidents": _incident_rows(conn, company_id)}
    finally:
        conn.close()


@router.post("/incidents")
def incidents_create(body: IncidentIn, company_id: str = Depends(require_workspace),
                     user: TokenPayload = Depends(get_current_user)):
    if body.severity not in _SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity must be one of {_SEVERITIES}")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO incidents (company_id, severity, title, detail, started_at, reported_by)
                   VALUES (%s, %s, %s, %s, COALESCE(%s::timestamptz, NOW()), %s) RETURNING id""",
                (company_id, body.severity, body.title.strip(), body.detail, body.started_at, user.sub))
            new_id = str(cur.fetchone()[0])
        conn.commit()
        return {"id": new_id}
    finally:
        conn.close()


@router.patch("/incidents/{incident_id}")
def incidents_update(incident_id: str, body: IncidentPatch,
                     company_id: str = Depends(require_workspace)):
    if body.severity is not None and body.severity not in _SEVERITIES:
        raise HTTPException(status_code=400, detail=f"severity must be one of {_SEVERITIES}")
    conn = _conn()
    try:
        sets, params = [], []
        if body.resolved is True:
            sets.append("resolved_at = COALESCE(resolved_at, NOW())")
        if body.resolved is False:
            sets.append("resolved_at = NULL")
        if body.detail is not None:
            sets.append("detail = %s"); params.append(body.detail)
        if body.severity is not None:
            sets.append("severity = %s"); params.append(body.severity)
        if not sets:
            return {"ok": True}
        with conn.cursor() as cur:
            cur.execute(f"UPDATE incidents SET {', '.join(sets)} WHERE id = %s AND (company_id = %s OR company_id IS NULL)",
                        (*params, incident_id, company_id))
            n = cur.rowcount
        conn.commit()
        if not n:
            raise HTTPException(status_code=404, detail="Incident not found")
        return {"ok": True}
    finally:
        conn.close()


# ── the board ─────────────────────────────────────────────────────────────────
def _month_end(start: date, months: int) -> date:
    y, m = start.year, start.month + months
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, min(start.day, 28))


@router.get("/milestones")
def milestone_board(company_id: str = Depends(require_workspace),
                    user: TokenPayload = Depends(get_current_user)):
    """Every Milestone-1 criterion with the live number behind it."""
    conn = _conn()
    try:
        _require_manager(conn, user)
        today = date.today()
        start_s = _setting(conn, "milestone_start_date", "2026-09-01")
        try:
            start = date.fromisoformat(start_s)
        except ValueError:
            start = date(2026, 9, 1)
        tracked = _setting(conn, "milestone_user_email", "") or ""
        dates = {
            "start": start.isoformat(),
            "month_3_demo": _month_end(start, 3).isoformat(),
            "month_6_review": _month_end(start, 6).isoformat(),
            "month_8_latest": _month_end(start, 8).isoformat(),
            "month_12_review": _month_end(start, 12).isoformat(),
            "month_24_review": _month_end(start, 24).isoformat(),
            "days_to_month_6": (_month_end(start, 6) - today).days,
        }

        # 1 · production — asserted from config; the UI shows the URLs
        # 2 · usage
        usage = U.stats(conn, tracked, window_days=200) if tracked else None
        # 3 · eval — latest recorded runs per runner
        with conn.cursor() as cur:
            cur.execute(
                """SELECT DISTINCT ON (runner) runner, ran_at, cases_run, passed,
                          citation_compliance, factual_accuracy, ship_blocked
                   FROM eval_runs ORDER BY runner, ran_at DESC""")
            evals = [{"runner": r[0], "ran_at": r[1].isoformat(), "cases_run": r[2], "passed": r[3],
                      "citation_compliance": float(r[4]),
                      "factual_accuracy": float(r[5]) if r[5] is not None else None,
                      "ship_blocked": bool(r[6])} for r in cur.fetchall()]
        # 4 · experiments
        xc = X.counts(conn, company_id)
        # 5 · incidents — critical in the last 60 days
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COUNT(*), MAX(started_at) FROM incidents
                   WHERE severity = 'critical' AND started_at >= NOW() - INTERVAL '60 days'
                     AND (company_id = %s OR company_id IS NULL)""", (company_id,))
            crit, last_crit = cur.fetchone()
        since_crit = None
        if last_crit:
            since_crit = (datetime.now(timezone.utc) - last_crit).days

        criteria = [
            {"key": "production", "title": "Dashboard live in production",
             "status": "met", "detail": "Vercel + Railway + Supabase; CI on every push",
             "value": None, "target": None},
            {"key": "usage", "title": "Owner active ≥ 4 days/week for 60 consecutive days",
             "status": ("met" if usage and usage["meets_60_days"] else
                        "in_progress" if usage and usage["active_days_in_window"] else "not_started"),
             "detail": (f"Tracking {tracked}" if tracked else "No tracked user set — choose one in settings"),
             "value": usage["best_run_days"] if usage else 0, "target": 60,
             "extra": usage},
            {"key": "eval", "title": "50-question set: ≥ 80% factual, 100% citation compliance",
             "status": ("met" if any(e["runner"] == "native" and e["cases_run"] >= 50
                                    and e["citation_compliance"] >= 1.0
                                    and (e["factual_accuracy"] or 0) >= 0.8 for e in evals)
                        else "in_progress" if evals else "not_started"),
             "detail": "Latest recorded harness runs per runner",
             "value": max((e["cases_run"] for e in evals), default=0), "target": 50,
             "extra": evals},
            {"key": "experiments", "title": "≥ 30 logged experiments with outcomes",
             "status": "met" if xc["with_outcomes"] >= 30 else ("in_progress" if xc["logged"] else "not_started"),
             "detail": f"{xc['logged']} logged · {xc['with_outcomes']} with outcomes · {xc['ai_suggested']} AI-suggested",
             "value": xc["with_outcomes"], "target": 30, "extra": xc},
            {"key": "demos", "title": "Month-3 demo passed; month-6 demo criteria met",
             "status": "not_started",
             "detail": f"Month-3 demo {dates['month_3_demo']} · Month-6 review {dates['month_6_review']} (see docs/reference/PLAN.md)",
             "value": None, "target": None},
            {"key": "incidents", "title": "No critical incident in the last 60 days",
             "status": "met" if not crit else "at_risk",
             "detail": (f"{crit} critical in 60 days" if crit else "None recorded"),
             "value": since_crit, "target": 60},
        ]
        return {"dates": dates, "tracked_user": tracked, "criteria": criteria}
    finally:
        conn.close()


class SettingsIn(BaseModel):
    milestone_start_date: str | None = None
    milestone_user_email: str | None = None


@router.get("/milestones/settings")
def milestone_settings(company_id: str = Depends(require_workspace),
                       user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        _require_manager(conn, user)
        return {"milestone_start_date": _setting(conn, "milestone_start_date", "2026-09-01"),
                "milestone_user_email": _setting(conn, "milestone_user_email", "")}
    finally:
        conn.close()


@router.put("/milestones/settings")
def milestone_settings_put(body: SettingsIn, company_id: str = Depends(require_workspace),
                           user: TokenPayload = Depends(get_current_user)):
    conn = _conn()
    try:
        _require_manager(conn, user)
        if body.milestone_start_date:
            date.fromisoformat(body.milestone_start_date)  # validate
            _set_setting(conn, "milestone_start_date", body.milestone_start_date)
        if body.milestone_user_email is not None:
            _set_setting(conn, "milestone_user_email", body.milestone_user_email.strip().lower())
        return {"ok": True}
    finally:
        conn.close()
