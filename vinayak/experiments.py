"""
experiments.py
───────────────
The experiments log — Milestone 1 evidence ("≥ 30 logged experiments with
outcomes captured") and the record the Strategy watcher writes its
suggestions into.

An experiment is a hypothesis with a metric, a window, and an outcome:
  proposed  → a person or the Strategy watcher suggested it
  accepted  → someone agreed to run it (decided_by)
  running   → started_at set; ends_at is when the metric is read
  closed    → result + outcome recorded (positive | negative | inconclusive)
  rejected  → not run

Only `closed` experiments count toward "with outcomes captured". The
Milestone board reads counts from here.
"""
from __future__ import annotations

import json
from datetime import date, datetime

_COLS = ["id", "company_id", "title", "hypothesis", "source", "status", "metric",
         "baseline", "target", "result", "outcome", "outcome_notes", "action_refs",
         "evidence", "proposed_by", "decided_by", "started_at", "ends_at", "closed_at",
         "created_at", "updated_at"]
_SELECT = "SELECT " + ", ".join(_COLS) + " FROM experiments"

STATUSES = ("proposed", "accepted", "running", "closed", "rejected")
OUTCOMES = ("positive", "negative", "inconclusive")
SOURCES = ("ai_suggested", "manual")


def _row(r) -> dict:
    d = dict(zip(_COLS, r))
    d["id"] = str(d["id"])
    for k in ("started_at", "ends_at"):
        d[k] = d[k].isoformat() if isinstance(d[k], date) else d[k]
    for k in ("closed_at", "created_at", "updated_at"):
        d[k] = d[k].isoformat() if isinstance(d[k], datetime) else d[k]
    for k in ("baseline", "target", "result"):
        d[k] = float(d[k]) if d[k] is not None else None
    return d


def create(conn, company_id: str, *, title: str, hypothesis: str | None = None,
           source: str = "manual", metric: str | None = None, baseline: float | None = None,
           target: float | None = None, action_refs: list | None = None,
           evidence: dict | None = None, proposed_by: str | None = None,
           started_at: str | None = None, ends_at: str | None = None,
           status: str = "proposed") -> dict:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO experiments
                 (company_id, title, hypothesis, source, status, metric, baseline, target,
                  action_refs, evidence, proposed_by, started_at, ends_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               RETURNING id""",
            (company_id, title.strip(), hypothesis, source, status, metric, baseline, target,
             json.dumps(action_refs or []), json.dumps(evidence or {}, default=str),
             proposed_by, started_at, ends_at),
        )
        new_id = cur.fetchone()[0]
        cur.execute(_SELECT + " WHERE id = %s", (new_id,))
        row = cur.fetchone()
    conn.commit()
    return _row(row)


def list_for(conn, company_id: str, status: str | None = None, limit: int = 200) -> list[dict]:
    with conn.cursor() as cur:
        if status:
            cur.execute(_SELECT + " WHERE company_id = %s AND status = %s ORDER BY created_at DESC LIMIT %s",
                        (company_id, status, limit))
        else:
            cur.execute(_SELECT + " WHERE company_id = %s ORDER BY created_at DESC LIMIT %s",
                        (company_id, limit))
        return [_row(r) for r in cur.fetchall()]


def get(conn, company_id: str, experiment_id: str) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(_SELECT + " WHERE id = %s AND company_id = %s", (experiment_id, company_id))
        row = cur.fetchone()
    return _row(row) if row else None


_UPDATABLE = {"title", "hypothesis", "metric", "baseline", "target", "result",
              "outcome", "outcome_notes", "action_refs", "evidence", "started_at", "ends_at"}


def update(conn, company_id: str, experiment_id: str, fields: dict, by: str | None = None) -> dict | None:
    """Update fields and/or transition status. Closing requires an outcome."""
    fields = {k: v for k, v in fields.items() if k in _UPDATABLE or k == "status"}
    status = fields.pop("status", None)
    sets, params = [], []
    for k, v in fields.items():
        if k in ("action_refs", "evidence"):
            v = json.dumps(v, default=str)
        sets.append(f"{k} = %s")
        params.append(v)
    if status:
        if status not in STATUSES:
            raise ValueError(f"status must be one of {STATUSES}")
        sets.append("status = %s"); params.append(status)
        if status in ("accepted", "rejected", "closed"):
            sets.append("decided_by = %s"); params.append(by)
        if status == "running":
            sets.append("started_at = COALESCE(started_at, CURRENT_DATE)")
        if status == "closed":
            sets.append("closed_at = NOW()")
    if status == "closed":
        outcome = fields.get("outcome")
        if outcome is None:
            # allow closing when an outcome was set earlier
            existing = get(conn, company_id, experiment_id)
            outcome = existing.get("outcome") if existing else None
        if outcome not in OUTCOMES:
            raise ValueError("closing an experiment requires outcome = positive | negative | inconclusive")
    if not sets:
        return get(conn, company_id, experiment_id)
    sets.append("updated_at = NOW()")
    with conn.cursor() as cur:
        cur.execute(f"UPDATE experiments SET {', '.join(sets)} WHERE id = %s AND company_id = %s",
                    (*params, experiment_id, company_id))
        cur.execute(_SELECT + " WHERE id = %s AND company_id = %s", (experiment_id, company_id))
        row = cur.fetchone()
    conn.commit()
    return _row(row) if row else None


def counts(conn, company_id: str | None = None) -> dict:
    """The Milestone-1 numbers: logged, with outcomes, AI-suggested, acted on."""
    where = "WHERE company_id = %s" if company_id else ""
    params = (company_id,) if company_id else ()
    with conn.cursor() as cur:
        cur.execute(
            f"""SELECT COUNT(*),
                       COUNT(*) FILTER (WHERE status = 'closed' AND outcome IS NOT NULL),
                       COUNT(*) FILTER (WHERE source = 'ai_suggested'),
                       COUNT(*) FILTER (WHERE source = 'ai_suggested' AND status IN ('accepted','running','closed')),
                       COUNT(*) FILTER (WHERE status = 'running'),
                       COUNT(*) FILTER (WHERE status = 'proposed')
                FROM experiments {where}""", params)
        r = cur.fetchone()
    return {"logged": int(r[0]), "with_outcomes": int(r[1]), "ai_suggested": int(r[2]),
            "ai_suggested_acted_on": int(r[3]), "running": int(r[4]), "proposed": int(r[5])}
