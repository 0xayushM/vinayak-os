"""
brain/strategy.py
──────────────────
The weekly watcher that turns what the Pulse noticed into things worth trying.

Milestone 1 asks for thirty logged experiments with outcomes. Thirty is a lot
to think of unprompted and almost none to accept when they arrive already
written, so this watcher does the thinking-of and a person does the deciding.
It reads the same Pulse signals the owner sees, and for each one it can act
on, files a *proposed* experiment carrying four things:

    a hypothesis   — what we think will happen, in the owner's language
    a metric       — a key from brain/metrics.py, so the result is a query
    a baseline     — the metric's value right now, captured at suggestion time
    a window       — how long to wait before reading it again

Nothing runs until somebody accepts it. Nothing is suggested twice while an
earlier version of it is still open, because each suggestion carries a dedupe
key and the unique index in migration 021 refuses the duplicate.

The suggestions are written by code, not by a model. Every sentence below is
a template filled with figures the query returned, which is the same rule the
Pulse cards and the morning brief follow: if a rupee figure appears in text a
person will act on, it came from the data, not from a language model.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from vinayak.brain import metrics
from vinayak.domain.money import Money

logger = logging.getLogger(__name__)

# Below these, a suggestion is noise rather than an opportunity.
MIN_DEAD_STOCK = 100_000.0
MIN_DRIFT = 50_000.0
MIN_CUSTOMER_OUTSTANDING = 25_000.0
CONCENTRATION_ALARM_PCT = 40.0

DEFAULT_MAX_SUGGESTIONS = 6


def _inr(v: float | None) -> str:
    return Money.compact(v)


def build_suggestions(pulse: dict, today: date) -> list[dict]:
    """Pure: signals in, suggestion dicts out. No database, no clock, no model
    — which is what makes the wording testable and the thresholds arguable."""
    out: list[dict] = []
    week = today.isocalendar()
    tag = f"{week[0]}W{week[1]:02d}"

    # ── 1. Money sliding into the worst buckets ──────────────────────────
    drift = pulse.get("aging_drift") or {}
    if not drift.get("history_building") and float(drift.get("drift", 0)) > MIN_DRIFT:
        movers = drift.get("movers", [])[:3]
        who = ", ".join(m["customer_name"] for m in movers) or "several accounts"
        out.append({
            "title": f"Chase the 60-plus book weekly for a month ({_inr(drift['drift'])} has slid)",
            "hypothesis": (
                f"{_inr(drift['drift'])} moved past 60 days in the last "
                f"{drift.get('window_days', 30)} days, mostly {who}. A weekly call or "
                f"reminder to just this bucket — rather than the whole ledger — should pull "
                f"the 60-plus total down within a month."),
            "metric_key": "ar.bucket_60plus",
            "window_days": 30,
            "dedupe_key": f"drift60:{tag}",
            "evidence": {"drift": drift.get("drift"), "movers": movers,
                         "bad_now": drift.get("bad_now")},
        })

    # ── 2. A customer who has quietly got slower ─────────────────────────
    behaviour = pulse.get("payment_behaviour") or {}
    for w in (behaviour.get("worsened") or [])[:1]:
        out.append({
            "title": f"Tighten terms with {w['customer_name']} — {w['days_slower']} days slower",
            "hypothesis": (
                f"{w['customer_name']} now takes {w['avg_now']} days to pay, against "
                f"{w['avg_before']} before. Asking for part-payment on despatch, or moving "
                f"them to a firmer reminder from the first day overdue, should bring their "
                f"outstanding down over the next six weeks."),
            "metric_key": "customer.outstanding",
            "entity_ref": f"customer:{w['customer_name']}",
            "window_days": 42,
            "dedupe_key": f"slow:{w['customer_name']}",
            "evidence": w,
        })
    # Fall back to the current book when there is no payment history yet.
    if not (behaviour.get("worsened") or []):
        for it in (behaviour.get("items") or [])[:1]:
            if it["overdue"] >= MIN_CUSTOMER_OUTSTANDING and it["oldest_days_overdue"] > 45:
                out.append({
                    "title": f"Put {it['customer_name']} on a payment plan — {_inr(it['overdue'])} overdue",
                    "hypothesis": (
                        f"{it['customer_name']} is carrying {_inr(it['overdue'])} overdue, the "
                        f"oldest {it['oldest_days_overdue']} days. Agreeing a written schedule of "
                        f"three instalments usually recovers more than repeated reminders do."),
                    "metric_key": "customer.outstanding",
                    "entity_ref": f"customer:{it['customer_name']}",
                    "window_days": 45,
                    "dedupe_key": f"plan:{it['customer_name']}",
                    "evidence": it,
                })

    # ── 3. Regulars who have gone quiet ──────────────────────────────────
    reorder = pulse.get("reorder") or {}
    quiet = reorder.get("items", [])[:5]
    if quiet:
        names = ", ".join(q["customer_name"] for q in quiet[:3])
        more = f" and {len(quiet) - 3} more" if len(quiet) > 3 else ""
        one = len(quiet) == 1
        out.append({
            "title": (f"Call {quiet[0]['customer_name']} — {quiet[0]['days_since_last']} days "
                      f"since their last order" if one else
                      f"Call {len(quiet)} regulars who are past their usual reorder gap"),
            "hypothesis": (
                (f"{names} buys about every {quiet[0]['median_gap_days']} days and has been "
                 f"quiet for {quiet[0]['days_since_last']} — {_inr(quiet[0]['avg_order_value'])} "
                 f"of typical order value. One call this week should tell us whether it is "
                 f"timing or a lost account.")
                if one else
                (f"{names}{more} each buy on a settled rhythm and are now past 1.5 times "
                 f"their own median gap — {_inr(reorder.get('value_at_stake', 0))} of typical "
                 f"order value between them. A single call each, this week, should bring at "
                 f"least half of them back within three weeks.")),
            "metric_key": "customer.days_quiet",
            "entity_ref": f"customer:{quiet[0]['customer_name']}",
            "window_days": 21,
            "dedupe_key": f"winback:{tag}",
            "evidence": {"customers": quiet,
                         "value_at_stake": reorder.get("value_at_stake")},
        })

    # ── 4. Capital sitting in stock nobody buys ──────────────────────────
    dead = pulse.get("dead_stock") or {}
    if float(dead.get("dead_value", 0)) > MIN_DEAD_STOCK:
        out.append({
            "title": f"Clear {_inr(dead['dead_value'])} of stock that has not sold in {dead.get('since_days', 90)} days",
            "hypothesis": (
                f"{dead.get('dead_count', 0)} items worth {_inr(dead['dead_value'])} have had no "
                f"sale in {dead.get('since_days', 90)} days. Offering them at a discount to the "
                f"customers who bought them before should turn part of it back into cash inside "
                f"six weeks — and what does not move at a discount is telling us to stop making it."),
            "metric_key": "inventory.dead_stock_value",
            "window_days": 42,
            "dedupe_key": f"deadstock:{tag}",
            "evidence": {"dead_value": dead.get("dead_value"),
                         "dead_count": dead.get("dead_count")},
        })

    # ── 5. Growing dependence on one customer ────────────────────────────
    conc = pulse.get("concentration") or {}
    if (float(conc.get("top1_pct", 0)) >= CONCENTRATION_ALARM_PCT
            and float(conc.get("top1_change", 0)) > 0):
        out.append({
            "title": f"Reduce dependence on {conc.get('top_customer')} — {conc['top1_pct']}% of revenue",
            "hypothesis": (
                f"{conc.get('top_customer')} is {conc['top1_pct']}% of the last "
                f"{conc.get('window_days', 90)} days of revenue, up {conc['top1_change']} points "
                f"on the period before. Winning or reviving two mid-sized accounts this quarter "
                f"should bring the top share down without losing volume."),
            "metric_key": "revenue.top1_share",
            "window_days": 90,
            "dedupe_key": f"concentration:{tag}",
            "evidence": {"top1_pct": conc.get("top1_pct"),
                         "top1_change": conc.get("top1_change"),
                         "top_customer": conc.get("top_customer")},
        })

    # ── 6. A vendor who has put prices up ────────────────────────────────
    for a in (pulse.get("anomalies") or {}).get("items", []):
        if a.get("kind") != "vendor_price_jump":
            continue
        vendor = a.get("vendor_name") or (a.get("entity_ref") or "").split(":", 1)[-1]
        item_code = a.get("item_code")
        if not item_code:
            continue
        out.append({
            "title": f"Requote {a.get('item_name') or item_code} against {vendor}'s price rise",
            "hypothesis": (
                f"{a['text']} Asking two alternate suppliers to quote the same item, and "
                f"showing the incumbent the result, usually recovers most of a rise like this. "
                f"The next purchase order for this item is the answer."),
            # The measured fact is the price on the NEXT order for this exact
            # vendor and item — which is why the reference carries both.
            "metric_key": "purchase.unit_price",
            "entity_ref": f"vendoritem:{vendor}|{item_code}",
            "window_days": 45,
            "dedupe_key": f"requote:{vendor}:{item_code}",
            "evidence": a,
        })
        break

    return out


def suggest(conn, company_id: str, *, config: dict | None = None) -> dict:
    """Read the Pulse, file the suggestions that are new. Returns run counts."""
    from vinayak import experiments as exp_log
    from vinayak.schema import pulse as P

    cfg = config or {}
    cap = int(cfg.get("max_suggestions", DEFAULT_MAX_SUGGESTIONS))
    today = date.today()

    signals: dict = {}
    for name, fn in (("aging_drift", P.get_aging_drift),
                     ("payment_behaviour", P.get_payment_behaviour),
                     ("reorder", P.get_reorder_status),
                     ("dead_stock", P.get_dead_stock_delta),
                     ("concentration", P.get_concentration_trend),
                     ("anomalies", P.get_anomalies)):
        try:
            signals[name] = fn(conn, company_id)
        except Exception as exc:  # noqa: BLE001 — one dead signal must not lose the rest
            logger.warning("strategy: signal %s failed for %s: %s", name, company_id, exc)
            signals[name] = {}

    filed = 0
    skipped = 0
    titles: list[str] = []
    for s in build_suggestions(signals, today)[:cap]:
        # The unique index in migration 021 is the real guarantee, but it only
        # bites on the UPDATE that stamps the key — so check first and avoid
        # creating a row we would immediately have to delete.
        if _already_open(conn, company_id, s["dedupe_key"]):
            skipped += 1
            continue
        baseline = metrics.read(conn, company_id, s["metric_key"], s.get("entity_ref"))
        m = metrics.METRICS.get(s["metric_key"])
        try:
            row = exp_log.create(
                conn, company_id,
                title=s["title"],
                hypothesis=s["hypothesis"],
                source="ai_suggested",
                metric=m.label if m else s["metric_key"],
                baseline=baseline,
                proposed_by="agent",
                evidence=s.get("evidence"),
                ends_at=(today + timedelta(days=s["window_days"])).isoformat(),
            )
        except Exception as exc:  # noqa: BLE001 — the dedupe index is the usual cause
            conn.rollback()
            skipped += 1
            logger.info("strategy: %s not filed (%s)", s["dedupe_key"], exc)
            continue
        try:
            _stamp(conn, row["id"], s, auto_close=not s.get("no_auto_close"))
        except Exception as exc:  # noqa: BLE001 — lost a race with another worker
            conn.rollback()
            _discard(conn, row["id"])
            skipped += 1
            logger.info("strategy: %s lost the dedupe race (%s)", s["dedupe_key"], exc)
            continue
        filed += 1
        titles.append(s["title"])

    if filed:
        summary = f"{filed} experiment{'s' if filed != 1 else ''} suggested."
    elif skipped:
        summary = (f"Nothing new — {skipped} earlier suggestion"
                   f"{'s are' if skipped > 1 else ' is'} still open.")
    else:
        summary = "Nothing worth suggesting this week."
    return {"suggested": filed, "already_open": skipped, "titles": titles,
            "summary": summary}


def _stamp(conn, experiment_id: str, s: dict, *, auto_close: bool) -> None:
    """Write the machine-readable half of the suggestion — the fields the
    experiments API does not expose to a person filling in the form."""
    with conn.cursor() as cur:
        cur.execute(
            """UPDATE experiments
                  SET metric_key = %s, window_days = %s, entity_ref = %s,
                      dedupe_key = %s, auto_close = %s
                WHERE id = %s""",
            (s["metric_key"], s["window_days"], s.get("entity_ref"),
             s["dedupe_key"], auto_close, experiment_id))
    conn.commit()


def _already_open(conn, company_id: str, dedupe_key: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT 1 FROM experiments
                WHERE company_id = %s AND dedupe_key = %s
                  AND status IN ('proposed','accepted','running') LIMIT 1""",
            (company_id, dedupe_key))
        return cur.fetchone() is not None


def _discard(conn, experiment_id: str) -> None:
    """Remove a suggestion that could not be stamped. It never reached a
    person, so deleting it is honest rather than destructive."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM experiments WHERE id = %s AND status = 'proposed'",
                    (experiment_id,))
    conn.commit()
