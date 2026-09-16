"""
api/routes/collections.py
──────────────────────────
Chasing money, as the screens need it.

  GET  /dashboard/collections              the chase list: who to call, and who
                                           is deliberately being left alone
  GET  /dashboard/collections/recovery     what chasing actually brought in
  POST /dashboard/collections/promise      "they said they'd pay on the 20th"
  POST /dashboard/collections/dispute      stop chasing this balance
  POST /dashboard/collections/pause        stop chasing until a date
  GET  /dashboard/collections/promises     the promise history

The two halves of the chase list matter equally. A collections screen that
shows only who to chase, and silently omits the disputed and the promised,
looks like it has lost them.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel

from vinayak import collections as C
from vinayak.api.deps import get_db as _conn, get_current_user, require_workspace, TokenPayload

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/collections")
def chase_list(limit: int = Query(default=15, le=100),
               company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return C.chase_list(conn, company_id, limit=limit)
    finally:
        conn.close()


@router.get("/collections/recovery")
def recovery(window_days: int = Query(default=C.RECOVERY_WINDOW_DAYS, ge=1, le=120),
             since_days: int = Query(default=90, ge=7, le=730),
             company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return C.recovery_stats(conn, company_id, window_days=window_days,
                                since_days=since_days)
    finally:
        conn.close()


class PromiseIn(BaseModel):
    customer_ref: str
    promised_on: str          # ISO date
    amount: float | None = None
    note: str | None = None


@router.post("/collections/promise")
def record_promise(body: PromiseIn, company_id: str = Depends(require_workspace),
                   user: TokenPayload = Depends(get_current_user)):
    """Record a promise to pay. Chasing pauses until the date plus grace.

    The most valuable thirty seconds anyone in accounts spends: the customer
    has just told them when the money is coming, and without this it lives in
    somebody's head until the next argument.
    """
    try:
        promised = date.fromisoformat(body.promised_on)
    except ValueError:
        raise HTTPException(400, "promised_on must be an ISO date (YYYY-MM-DD)")
    if promised < date.today() - timedelta(days=365):
        raise HTTPException(400, "that date is more than a year in the past")
    conn = _conn()
    try:
        p = C.record_promise(conn, company_id, body.customer_ref.strip(), promised,
                             amount=body.amount, note=body.note, recorded_by=user.sub)
        return {"promise": p}
    finally:
        conn.close()


class DisputeIn(BaseModel):
    customer_ref: str
    disputed: bool = True
    note: str | None = None


@router.post("/collections/dispute")
def set_dispute(body: DisputeIn, company_id: str = Depends(require_workspace),
                user: TokenPayload = Depends(get_current_user)):
    """Flag or clear a dispute. A disputed balance is never chased
    automatically — the argument is about the invoice, and a reminder makes
    it worse."""
    conn = _conn()
    try:
        C.set_dispute(conn, company_id, body.customer_ref.strip(), body.disputed,
                      note=body.note)
        logger.info("collections: %s marked %s disputed=%s",
                    user.sub, body.customer_ref, body.disputed)
        return {"ok": True, "customer_ref": body.customer_ref,
                "disputed": body.disputed}
    finally:
        conn.close()


class PauseIn(BaseModel):
    customer_ref: str
    until: str
    reason: str | None = None


@router.post("/collections/pause")
def pause(body: PauseIn, company_id: str = Depends(require_workspace)):
    try:
        until = date.fromisoformat(body.until)
    except ValueError:
        raise HTTPException(400, "until must be an ISO date (YYYY-MM-DD)")
    conn = _conn()
    try:
        C.pause(conn, company_id, body.customer_ref.strip(), until, reason=body.reason)
        return {"ok": True, "customer_ref": body.customer_ref, "until": body.until}
    finally:
        conn.close()


@router.get("/collections/promises")
def promises(customer_ref: str | None = Query(default=None),
             company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        return {"promises": C.promise_history(conn, company_id, customer_ref)}
    finally:
        conn.close()


# ── Credit flags: what Accounts knows, where Sales sees it ───────────────

@router.get("/flags")
def live_flags(company_id: str = Depends(require_workspace)):
    """Every live credit flag, keyed by customer.

    One request decorates every screen that names a customer — quotes, orders,
    the customer list. Fetching per row would be the same information at
    twenty times the cost, and the set is small by construction because a flag
    is only raised when something is actually wrong.
    """
    from vinayak import flags as F
    conn = _conn()
    try:
        flags = F.live(conn, company_id)
        return {"flags": flags,
                "hold_count": sum(1 for f in flags.values() if f["level"] == "hold"),
                "watch_count": sum(1 for f in flags.values() if f["level"] == "watch")}
    finally:
        conn.close()


class FlagActionIn(BaseModel):
    customer_ref: str
    note: str | None = None


@router.post("/flags/clear")
def clear_flag(body: FlagActionIn, company_id: str = Depends(require_workspace),
               user: TokenPayload = Depends(get_current_user)):
    """Take the flag down. The history stays."""
    from vinayak import flags as F
    conn = _conn()
    try:
        ok = F.clear(conn, company_id, body.customer_ref.strip(), by=user.sub,
                     reason=body.note)
        return {"ok": ok, "customer_ref": body.customer_ref}
    finally:
        conn.close()


@router.post("/flags/override")
def override_flag(body: FlagActionIn, company_id: str = Depends(require_workspace),
                  user: TokenPayload = Depends(get_current_user)):
    """"I know, and I'm fine with it."

    Keeps the flag on record but stops it driving anything, and stops the
    detector raising it again. A machine that re-raises over a person's
    judgement is one they learn to switch off entirely.
    """
    from vinayak import flags as F
    conn = _conn()
    try:
        ok = F.override(conn, company_id, body.customer_ref.strip(), by=user.sub,
                        note=body.note)
        return {"ok": ok, "customer_ref": body.customer_ref}
    finally:
        conn.close()


@router.get("/flags/{customer_ref}/history")
def flag_history(customer_ref: str, company_id: str = Depends(require_workspace)):
    from vinayak import flags as F
    conn = _conn()
    try:
        return {"history": F.history(conn, company_id, customer_ref)}
    finally:
        conn.close()
