"""
api/routes/pulse.py
────────────────────
The Pulse — the landing surface.

  GET /dashboard/pulse            every card, ordered for the caller's role
                                  (or their pinned order), urgent first
  GET /dashboard/pulse/{key}      one card, for a deep link or a refresh
  GET /dashboard/payments/inferred  the payment dates learned from AR history

The same payload is what the morning brief is written from, so a card only
has to be built once. Read-only; scoped like every other route.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from vinayak.api.deps import get_db as _conn, get_current_user, require_workspace, TokenPayload
from vinayak.schema import pulse as P
from vinayak.schema import pulse_cards as C

logger = logging.getLogger(__name__)
router = APIRouter()


def _reader(conn, user: TokenPayload) -> tuple[str | None, list[str] | None]:
    """The caller's role and pinned card order, which decide the layout."""
    try:
        from vinayak.api.routes.milestones import user_record
        rec = user_record(conn, user.sub)
        role = rec.get("role")
        if role in (None, "", "admin"):
            role = "owner"
        pinned = rec.get("pinned_cards")
        return role, (pinned if isinstance(pinned, list) and pinned else None)
    except Exception as exc:  # noqa: BLE001 — layout is a preference, never a gate
        # Roll the connection back before returning. A failed SELECT leaves the
        # transaction aborted, and every later query on this connection then
        # fails too — which is how a preference lookup used to take the whole
        # page down with it.
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.warning("pulse: could not read role for %s: %s", user.sub, exc)
        return "owner", None


@router.get("/pulse")
def pulse(sort: str = Query(default="role", pattern="^(role|severity)$"),
          company_id: str = Depends(require_workspace),
          user: TokenPayload = Depends(get_current_user)):
    """The Today page.

    This endpoint never returns an error. Today is the page the owner opens
    first, and a blank one with 'Internal server error' on it is worse than
    any partial answer — it tells him nothing and gives him nowhere to go. So
    a failure here becomes a card that says what broke, with the traceback in
    the server log where it belongs.
    """
    conn = _conn()
    try:
        role, pinned = _reader(conn, user)
        return C.build_cards(conn, company_id, role=role, pinned=pinned, sort=sort)
    except Exception as exc:  # noqa: BLE001
        logger.exception("pulse failed for %s", company_id)
        return {"cards": [C._card(
                    "pulse_unavailable", "Today could not be built", 0, display="—",
                    why=("Something went wrong assembling your cards. The rest of the "
                         "dashboard is unaffected — the detail is in the server log."),
                    action={"label": "Open Money in", "kind": "open",
                            "params": {"path": "/dashboard/money-in"}},
                    confidence=P.UNCERTAIN, severity=0)],
                "role": None, "failed": ["all"], "needs_attention": 0,
                "no_data": False, "error": str(exc)[:300]}
    finally:
        conn.close()


@router.get("/pulse/{key}")
def pulse_card(key: str, company_id: str = Depends(require_workspace)):
    conn = _conn()
    try:
        for k, query_fn, card_fn in C._BUILDERS:
            if k == key:
                return {"card": card_fn(query_fn(conn, company_id))}
        raise HTTPException(status_code=404, detail=f"No such card: {key}")
    finally:
        conn.close()


@router.get("/brief")
def brief_preview(company_id: str = Depends(require_workspace),
                  user: TokenPayload = Depends(get_current_user)):
    """Exactly what the 06:00 brief will say, so it can be read (and checked)
    at any hour without sending anything."""
    from vinayak.brief import build_brief
    conn = _conn()
    try:
        role, _pinned = _reader(conn, user)
        b = build_brief(conn, company_id, role=role)
        return {"subject": b["subject"], "text": b["text"], "html": b["html"],
                "card_count": len(b["cards"]), "urgent": b.get("urgent", 0),
                "no_data": b.get("no_data", False)}
    finally:
        conn.close()


@router.post("/brief/send")
def brief_send(to: str | None = Query(default=None),
               company_id: str = Depends(require_workspace),
               user: TokenPayload = Depends(get_current_user)):
    """Send this workspace's brief now — to one address, or to everyone who
    would receive the scheduled one. Used to prove delivery on day one."""
    from vinayak.brief import send_brief
    conn = _conn()
    try:
        role, _pinned = _reader(conn, user)
        return send_brief(conn, company_id, to=to, role=role)
    finally:
        conn.close()


@router.get("/payments/inferred")
def inferred_payments(window_days: int = Query(default=180, ge=7, le=730),
                      company_id: str = Depends(require_workspace)):
    """Payment dates learned by watching the AR book empty out — the basis for
    real days-to-pay, DSO trend and the collections recovery proof."""
    conn = _conn()
    try:
        return P.get_inferred_payments(conn, company_id, window_days=window_days)
    finally:
        conn.close()
