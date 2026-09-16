"""
collections.py
───────────────
Chasing money, as a process rather than a message.

Sprint 2 could draft a reminder. What it could not do is remember it had sent
one, which is the whole difference between chasing and nagging — and nagging
is how a supplier relationship gets damaged while the money stays unpaid.

Four ideas, in the order they matter:

**The ladder.** A customer moves up rungs R1–R4 as a balance stays unpaid.
The fourth letter should not read like the first, and each rung is slower and
firmer than the last. The ladder climbs on lateness *and* on silence: three
ignored reminders is information, and it moves the customer up whatever the
calendar says.

**The promise.** "We'll pay on the 20th" is the single most useful fact a
collections process can hold and the one least often written down. Recorded,
it pauses chasing until the 20th — because chasing someone who has already
told you when they will pay is exactly how you lose their goodwill for nothing.
Broken, it is an event, and a customer who breaks promises is a different
credit risk from one who is merely slow.

**The dispute.** A disputed balance is never chased automatically. The
argument is about the invoice, and a reminder makes it worse.

**The proof.** Every reminder that actually goes out is logged with the
balance at that moment, so "₹X recovered within 14 days of a chase" is a
measurement rather than a claim. That number is the one that justifies the
product's existence, so it has to be built from facts nobody chose after the
event.

Everything that decides wording or eligibility is a pure function, so the
judgement can be argued with in a test rather than in production.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

from vinayak.domain.money import Money

logger = logging.getLogger(__name__)

# ── The ladder ────────────────────────────────────────────────────────────
# Each rung: the lateness that earns it, the days to wait before the next
# reminder, and the name of its tone.
@dataclass(frozen=True)
class Rung:
    level: int
    from_days: int          # days past due at which this rung becomes available
    cooldown_days: int      # minimum gap before the next chase
    tone: str
    label: str


LADDER: tuple[Rung, ...] = (
    Rung(1, 7,  10, "gentle",  "A reminder"),
    Rung(2, 30, 10, "firm",    "A firmer reminder"),
    Rung(3, 60, 14, "final",   "Final notice before credit hold"),
    Rung(4, 90, 21, "hold",    "Account on hold, escalated"),
)

MAX_RUNG = LADDER[-1].level

# How many ignored reminders push a customer up a rung regardless of the
# calendar. Silence is information.
IGNORED_CHASES_TO_ESCALATE = 2

# A promise buys this much grace after the promised day before it is called
# broken — cheques clear late and banks are slow, and calling a promise broken
# on the morning after is the kind of accuracy that loses customers.
PROMISE_GRACE_DAYS = 3

# The window recovery is measured over. Long enough for a payment run,
# short enough that the chase is a plausible cause.
RECOVERY_WINDOW_DAYS = 14


def rung_for(days_overdue: int, chases_sent: int = 0, current_rung: int = 0) -> int:
    """Which rung this balance has earned. 0 means "not late enough to chase".

    **A ladder is climbed one rung at a time.** Lateness says how high a
    customer *could* be; `current_rung` says how high we have actually taken
    them, and the next chase is at most one step above it. Without that rule,
    switching the product on with a neglected ledger sends "your account is on
    hold" as the first thing a customer has ever heard from us — because they
    are 140 days late and we have never asked. That is unfair, commercially
    stupid, and the fastest way to make the owner turn chasing off.

    So a never-chased customer gets a gentle reminder however late they are,
    and earns the firmer ones by not replying.
    """
    earned = 0
    for r in LADDER:
        if days_overdue >= r.from_days:
            earned = r.level
    if earned == 0:
        return 0
    # Silence escalates: two reminders with nothing back moves them up one.
    earned = min(MAX_RUNG, earned + (chases_sent // IGNORED_CHASES_TO_ESCALATE))
    return min(earned, int(current_rung or 0) + 1)


def rung(level: int) -> Rung:
    return LADDER[max(1, min(MAX_RUNG, level)) - 1]


# ── May we chase at all? ──────────────────────────────────────────────────
@dataclass(frozen=True)
class ChaseDecision:
    allowed: bool
    rung: int
    reason: str


def decide(*, days_overdue: int, outstanding: float, state: dict | None,
           open_promise: dict | None, today: date | None = None,
           min_amount: float = 5_000.0) -> ChaseDecision:
    """Everything that stands between an overdue invoice and a reminder.

    Pure on purpose. Every one of these rules is a judgement someone could
    reasonably disagree with, and an argument about collections policy should
    happen over a test, not over a customer's inbox.
    """
    today = today or date.today()
    st = state or {}

    if st.get("disputed"):
        return ChaseDecision(False, 0, "the balance is disputed")

    if outstanding < min_amount:
        return ChaseDecision(False, 0, "below the amount worth chasing")

    if open_promise:
        promised = open_promise.get("promised_on")
        if isinstance(promised, str):
            promised = date.fromisoformat(promised)
        if promised and today <= promised + timedelta(days=PROMISE_GRACE_DAYS):
            return ChaseDecision(False, 0,
                                 f"they promised to pay on {promised.isoformat()}")

    paused = st.get("paused_until")
    if isinstance(paused, str):
        paused = date.fromisoformat(paused)
    if paused and today <= paused:
        return ChaseDecision(False, 0, st.get("pause_reason") or "chasing is paused")

    level = rung_for(days_overdue, int(st.get("chases_sent") or 0),
                     int(st.get("rung") or 0))
    if level == 0:
        return ChaseDecision(False, 0, "not late enough yet")

    last = st.get("last_chased_at")
    if last:
        if isinstance(last, str):
            last = datetime.fromisoformat(last)
        if isinstance(last, datetime):
            last_day = last.astimezone(timezone.utc).date() if last.tzinfo else last.date()
        else:
            last_day = last
        gap = (today - last_day).days
        needed = rung(level).cooldown_days
        if gap < needed:
            return ChaseDecision(False, level,
                                 f"chased {gap} day{'s' if gap != 1 else ''} ago; "
                                 f"rung {level} waits {needed}")

    return ChaseDecision(True, level, rung(level).label)


# ── The wording ───────────────────────────────────────────────────────────
def compose(customer: str, outstanding: float, overdue: float, oldest_days: int,
            level: int) -> tuple[str, str]:
    """The reminder at a given rung. Pure, deterministic, no model.

    The amount is always the overdue figure where there is one, because that
    is the number being asked for. The escalation is in what is asked and what
    happens next — not in adjectives.
    """
    r = rung(level)
    amt = Money.compact(overdue if overdue > 0 else outstanding)
    aged = f" (oldest {oldest_days} days)" if oldest_days and oldest_days > 0 else ""

    if r.tone == "gentle":
        return (f"Gentle reminder: {amt} outstanding",
                f"Dear {customer},\n\n"
                f"A gentle reminder that {amt} is currently outstanding on your account{aged}. "
                "If payment is already on its way, please ignore this note — otherwise we'd "
                "appreciate a quick update on timing.\n\nWarm regards,\nAccounts")

    if r.tone == "firm":
        return (f"Payment overdue: {amt} — action needed",
                f"Dear {customer},\n\n"
                f"Our records show {amt} overdue on your account{aged}. This is our second "
                "reminder. Please arrange payment, or reply with the date we can expect it so "
                "we can update our records.\n\nRegards,\nAccounts")

    if r.tone == "final":
        return (f"Final notice: {amt} overdue",
                f"Dear {customer},\n\n"
                f"{amt} remains overdue on your account{aged}, and earlier reminders have gone "
                "unanswered. Unless we receive payment or an agreed schedule within seven days, "
                "we will place the account on credit hold, which will affect pending and future "
                "orders.\n\nWe would much rather agree a schedule. Please call us.\n\n"
                "Regards,\nAccounts")

    return (f"Account on hold: {amt} overdue",
            f"Dear {customer},\n\n"
            f"{amt} remains unpaid{aged} and your account has been placed on credit hold; new "
            "orders cannot be released until the balance is cleared or a schedule is agreed.\n\n"
            "We want to resolve this. Please contact us so we can agree a way forward.\n\n"
            "Regards,\nAccounts")


# ── Priority: which chase is worth making first ──────────────────────────
def chase_priority(outstanding: float, days_overdue: int,
                   behaviour_score: float = 0.0) -> float:
    """Recovery impact, not size.

    Amount alone sends you after the biggest customer, who is often simply on
    long terms and will pay. Lateness alone sends you after a trivial invoice
    from two years ago. The product of the two, weighted by how this customer
    has actually behaved, ranks the call that recovers the most.

    behaviour_score is 0–1 from the Pulse's payment-behaviour composite, where
    higher means worse. It multiplies rather than adds, so a reliable payer who
    is merely late stays below an unreliable one at the same amount and age.
    """
    if outstanding <= 0 or days_overdue <= 0:
        return 0.0
    lateness = min(days_overdue, 365) / 30.0          # in months, capped at a year
    return round(outstanding * lateness * (1.0 + behaviour_score), 2)


# ══════════════════════════════════════════════════════════════════════════
# The stored half
# ──────────────────────────────────────────────────────────────────────────
# Everything above decides; everything below remembers. Kept apart so the
# judgements stay testable without a database.
# ══════════════════════════════════════════════════════════════════════════

def get_state(conn, company_id: str, customer_ref: str) -> dict:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT rung, last_chased_at, last_rung_at, chases_sent, paused_until,
                      pause_reason, disputed, dispute_note
                 FROM collections_state
                WHERE company_id = %s AND customer_ref = %s""",
            (company_id, customer_ref))
        r = cur.fetchone()
    if not r:
        return {"rung": 0, "chases_sent": 0, "disputed": False}
    return {"rung": int(r[0] or 0), "last_chased_at": r[1], "last_rung_at": r[2],
            "chases_sent": int(r[3] or 0), "paused_until": r[4],
            "pause_reason": r[5], "disputed": bool(r[6]), "dispute_note": r[7]}


def all_states(conn, company_id: str) -> dict[str, dict]:
    """Every customer's state in one read — the chase list needs them all and
    would otherwise do one query per customer."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT customer_ref, rung, last_chased_at, chases_sent, paused_until,
                      pause_reason, disputed
                 FROM collections_state WHERE company_id = %s""", (company_id,))
        rows = cur.fetchall()
    return {r[0]: {"rung": int(r[1] or 0), "last_chased_at": r[2],
                   "chases_sent": int(r[3] or 0), "paused_until": r[4],
                   "pause_reason": r[5], "disputed": bool(r[6])} for r in rows}


def _ensure(conn, company_id: str, customer_ref: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO collections_state (company_id, customer_ref)
               VALUES (%s, %s) ON CONFLICT DO NOTHING""", (company_id, customer_ref))


def record_chase(conn, company_id: str, customer_ref: str, level: int, *,
                 action_id: str | None = None, balance: float | None = None,
                 approved_by: str | None = None, channel: str = "email") -> None:
    """A reminder actually went out. This is the moment recovery is measured
    from, which is why the balance at this instant is captured with it."""
    _ensure(conn, company_id, customer_ref)
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO chase_log (company_id, customer_ref, rung, action_id,
                                      channel, balance_at_send, approved_by)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (company_id, customer_ref, level, action_id, channel, balance, approved_by))
        cur.execute(
            """UPDATE collections_state
                  SET rung = GREATEST(rung, %s), last_chased_at = NOW(),
                      last_rung_at = CASE WHEN %s > rung THEN NOW() ELSE last_rung_at END,
                      chases_sent = chases_sent + 1, updated_at = NOW()
                WHERE company_id = %s AND customer_ref = %s""",
            (level, level, company_id, customer_ref))
    conn.commit()


def set_dispute(conn, company_id: str, customer_ref: str, disputed: bool,
                note: str | None = None) -> None:
    _ensure(conn, company_id, customer_ref)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE collections_state
                  SET disputed = %s, dispute_note = %s,
                      disputed_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                      updated_at = NOW()
                WHERE company_id = %s AND customer_ref = %s""",
            (disputed, note, disputed, company_id, customer_ref))
    conn.commit()


def pause(conn, company_id: str, customer_ref: str, until: date,
          reason: str | None = None) -> None:
    _ensure(conn, company_id, customer_ref)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE collections_state SET paused_until = %s, pause_reason = %s,
                      updated_at = NOW()
                WHERE company_id = %s AND customer_ref = %s""",
            (until, reason, company_id, customer_ref))
    conn.commit()


def reset_if_settled(conn, company_id: str) -> int:
    """A customer who has cleared their balance starts again at the bottom of
    the ladder. Without this, someone who paid in March is still on 'final
    notice' in September, and the next reminder they get is the wrong one."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE collections_state s
                  SET rung = 0, chases_sent = 0, paused_until = NULL,
                      pause_reason = NULL, updated_at = NOW()
                WHERE s.company_id = %s AND (s.rung > 0 OR s.chases_sent > 0)
                  AND NOT EXISTS (
                      SELECT 1 FROM canon_ar_flat a
                       WHERE a.company_id = s.company_id
                         AND a.customer_name = s.customer_ref
                         AND COALESCE(a.outstanding_amount, 0) > 0)""",
            (company_id,))
        n = cur.rowcount or 0
    conn.commit()
    return n


# ── Promises ──────────────────────────────────────────────────────────────

def record_promise(conn, company_id: str, customer_ref: str, promised_on: str | date,
                   *, amount: float | None = None, note: str | None = None,
                   recorded_by: str | None = None) -> dict:
    """Record "they said they'd pay on X". Pauses chasing until then."""
    if isinstance(promised_on, str):
        promised_on = date.fromisoformat(promised_on)
    with conn.cursor() as cur:
        cur.execute("""SELECT COALESCE(SUM(outstanding_amount),0) FROM canon_ar_flat
                        WHERE company_id=%s AND customer_name=%s""",
                    (company_id, customer_ref))
        balance = float(cur.fetchone()[0] or 0)
        # A new promise supersedes an open one — the customer has given a new
        # date, and holding both would mean chasing against the older of them.
        cur.execute(
            """UPDATE promises SET status = 'cancelled', settled_at = NOW()
                WHERE company_id = %s AND customer_ref = %s AND status = 'open'""",
            (company_id, customer_ref))
        cur.execute(
            """INSERT INTO promises (company_id, customer_ref, amount, promised_on,
                                     note, recorded_by, balance_at_promise)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (company_id, customer_ref, amount, promised_on, note, recorded_by, balance))
        pid = str(cur.fetchone()[0])
    _ensure(conn, company_id, customer_ref)
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE collections_state
                  SET paused_until = %s, pause_reason = %s, updated_at = NOW()
                WHERE company_id = %s AND customer_ref = %s""",
            (promised_on + timedelta(days=PROMISE_GRACE_DAYS),
             f"promised to pay on {promised_on.isoformat()}", company_id, customer_ref))
    conn.commit()
    return {"id": pid, "customer_ref": customer_ref,
            "promised_on": promised_on.isoformat(), "amount": amount,
            "balance_at_promise": balance, "status": "open"}


def open_promises(conn, company_id: str) -> dict[str, dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT ON (customer_ref) customer_ref, id, promised_on, amount,
                      balance_at_promise
                 FROM promises
                WHERE company_id = %s AND status = 'open'
                ORDER BY customer_ref, created_at DESC""", (company_id,))
        rows = cur.fetchall()
    return {r[0]: {"id": str(r[1]), "promised_on": r[2],
                   "amount": float(r[3]) if r[3] is not None else None,
                   "balance_at_promise": float(r[4] or 0)} for r in rows}


def settle_due_promises(conn, company_id: str, today: date | None = None) -> dict:
    """Judge every promise whose day has passed.

    Kept when the balance came down by at least what was promised (or by
    anything at all, when no amount was named). Broken otherwise. The
    comparison is against the balance recorded WHEN THE PROMISE WAS MADE —
    new invoices raised since then are not a reason to call a promise broken.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=PROMISE_GRACE_DAYS)
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, customer_ref, amount, balance_at_promise, promised_on
                 FROM promises
                WHERE company_id = %s AND status = 'open' AND promised_on <= %s""",
            (company_id, cutoff))
        due = cur.fetchall()

    kept, broken = [], []
    for pid, customer, amount, before, promised_on in due:
        with conn.cursor() as cur:
            cur.execute("""SELECT COALESCE(SUM(outstanding_amount),0) FROM canon_ar_flat
                            WHERE company_id=%s AND customer_name=%s""",
                        (company_id, customer))
            now_balance = float(cur.fetchone()[0] or 0)
        before = float(before or 0)
        paid = before - now_balance
        needed = float(amount) if amount is not None else 1.0
        ok = paid >= needed
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE promises SET status = %s, settled_at = NOW() WHERE id = %s""",
                ("kept" if ok else "broken", pid))
        (kept if ok else broken).append(
            {"id": str(pid), "customer_ref": customer, "paid": paid,
             "promised": needed if amount is not None else None,
             "promised_on": promised_on.isoformat() if promised_on else None})
    if due:
        conn.commit()
    return {"kept": kept, "broken": broken, "checked": len(due)}


def promise_history(conn, company_id: str, customer_ref: str | None = None,
                    limit: int = 100) -> list[dict]:
    sql = """SELECT id, customer_ref, amount, promised_on, made_on, status, note
               FROM promises WHERE company_id = %s"""
    params: list = [company_id]
    if customer_ref:
        sql += " AND customer_ref = %s"
        params.append(customer_ref)
    sql += " ORDER BY created_at DESC LIMIT %s"
    params.append(limit)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [{"id": str(r[0]), "customer_ref": r[1],
             "amount": float(r[2]) if r[2] is not None else None,
             "promised_on": r[3].isoformat() if r[3] else None,
             "made_on": r[4].isoformat() if r[4] else None,
             "status": r[5], "note": r[6]} for r in rows]


# ── The proof ─────────────────────────────────────────────────────────────

def recovery_stats(conn, company_id: str, window_days: int = RECOVERY_WINDOW_DAYS,
                   since_days: int = 90) -> dict:
    """Rupees that came in within `window_days` of a reminder going out.

    Built from two facts nobody chose after the event: the balance captured at
    the moment each reminder was sent, and the same customer's balance
    `window_days` later, read from the daily receivables snapshot. Neither can
    be adjusted to flatter the result.

    **This is correlation, and the function says so.** Some of these customers
    would have paid anyway; a chase is one cause among several. What the number
    honestly supports is "₹X came in from chased accounts inside a fortnight",
    which is worth saying, and not "the product recovered ₹X", which is not.
    The way to close that gap is a hold-back — chase four of five and leave the
    fifth — and that is an experiment the Strategy watcher can propose.
    """
    with conn.cursor() as cur:
        cur.execute(
            """SELECT c.id, c.customer_ref, c.rung, c.sent_at::date, c.balance_at_send
                 FROM chase_log c
                WHERE c.company_id = %s
                  AND c.sent_at >= CURRENT_DATE - %s
                  AND c.balance_at_send IS NOT NULL
                ORDER BY c.sent_at DESC""",
            (company_id, since_days))
        chases = cur.fetchall()

    if not chases:
        return {"chases": 0, "measurable": 0, "recovered": 0.0, "chased_value": 0.0,
                "recovery_rate_pct": 0.0, "window_days": window_days,
                "since_days": since_days, "by_rung": {}, "no_history": True}

    from vinayak.schema.pulse import snapshot_dates, _nearest_snapshot
    dates = snapshot_dates(conn, company_id)

    recovered = 0.0
    chased_value = 0.0
    measurable = 0
    by_rung: dict[int, dict] = {}
    for _cid, customer, level, sent_on, before in chases:
        before = float(before or 0)
        target = sent_on + timedelta(days=window_days)
        snap = _nearest_snapshot(dates, target) if dates else None
        # No snapshot on or after the window's end means the fortnight has not
        # finished yet. Counting those as zero recovery would quietly drag the
        # rate down with every fresh chase.
        if snap is None or snap < target:
            continue
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COALESCE(SUM(outstanding),0) FROM ar_daily_snapshot
                    WHERE company_id=%s AND snap_date=%s AND customer_name=%s""",
                (company_id, snap, customer))
            after = float(cur.fetchone()[0] or 0)
        paid = max(0.0, before - after)
        measurable += 1
        recovered += paid
        chased_value += before
        r = by_rung.setdefault(int(level), {"chases": 0, "recovered": 0.0, "chased": 0.0})
        r["chases"] += 1
        r["recovered"] += paid
        r["chased"] += before

    return {
        "chases": len(chases),
        "measurable": measurable,
        "recovered": round(recovered, 2),
        "chased_value": round(chased_value, 2),
        "recovery_rate_pct": round(recovered / chased_value * 100, 1) if chased_value else 0.0,
        "window_days": window_days,
        "since_days": since_days,
        "by_rung": {k: {"chases": v["chases"], "recovered": round(v["recovered"], 2),
                        "rate_pct": round(v["recovered"] / v["chased"] * 100, 1)
                                    if v["chased"] else 0.0}
                    for k, v in sorted(by_rung.items())},
        "no_history": False,
        "caveat": ("Money that arrived within the window, not money the chase caused. "
                   "A hold-back experiment is what would separate the two."),
    }


def chase_list(conn, company_id: str, limit: int = 15) -> dict:
    """Who to call, in the order that recovers the most — and who is
    deliberately being left alone, which is the half a chase list usually
    hides. A collections screen that silently omits the disputed and the
    promised looks like it has lost them."""
    from vinayak.schema.pulse import get_payment_behaviour

    with conn.cursor() as cur:
        cur.execute(
            """SELECT customer_name,
                      COALESCE(SUM(outstanding_amount), 0)                       AS outstanding,
                      MAX(CURRENT_DATE - due_date)                               AS oldest
                 FROM canon_ar_flat
                WHERE company_id = %s AND COALESCE(outstanding_amount, 0) > 0
                  AND due_date IS NOT NULL AND due_date < CURRENT_DATE
                GROUP BY customer_name""", (company_id,))
        rows = cur.fetchall()

    states = all_states(conn, company_id)
    promises = open_promises(conn, company_id)
    try:
        behaviour = {i["customer_name"]: i["score"]
                     for i in get_payment_behaviour(conn, company_id, top_n=200)["items"]}
    except Exception as exc:  # noqa: BLE001 — ranking is better with it, fine without
        logger.warning("chase_list: behaviour unavailable for %s: %s", company_id, exc)
        behaviour = {}

    due, held = [], []
    for customer, outstanding, oldest in rows:
        outstanding, oldest = float(outstanding or 0), int(oldest or 0)
        d = decide(days_overdue=oldest, outstanding=outstanding,
                   state=states.get(customer), open_promise=promises.get(customer))
        row = {"customer_name": customer, "outstanding": outstanding,
               "days_overdue": oldest, "rung": d.rung,
               "rung_label": rung(d.rung).label if d.rung else None,
               "priority": chase_priority(outstanding, oldest, behaviour.get(customer, 0.0)),
               "reason": d.reason}
        (due if d.allowed else held).append(row)

    due.sort(key=lambda r: r["priority"], reverse=True)
    held.sort(key=lambda r: r["outstanding"], reverse=True)
    return {"due": due[:limit], "held": held[:limit],
            "due_count": len(due), "held_count": len(held),
            "due_value": round(sum(r["outstanding"] for r in due), 2),
            "held_value": round(sum(r["outstanding"] for r in held), 2)}
