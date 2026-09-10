"""
schema/pulse_cards.py
──────────────────────
Turns the Pulse query results into CARDS — the one shape the landing page,
the morning brief and (later) the WhatsApp message all render.

The card contract, so every surface can be dumb:

    key         stable id, used for pinning and ordering
    title       what it answers, in the owner's words
    headline    {value, display}          the figure
    change      {value, display, direction, label}   vs this business's own normal
    why         one sentence naming the cause
    items       the few rows behind it (capped)
    action      {label, kind, params} | None — what can be started here
    confidence  CERTAIN | PROBABLE | UNCERTAIN, computed from the data, not guessed
    severity    0–100, how loudly it should ask for attention (sort key)
    stale / last_synced_at

Nothing here computes a business number: it only formats what the query
functions returned. A card whose data is missing or still accumulating says
so and drops down the order rather than showing a zero.
"""
from __future__ import annotations

import logging

from vinayak.domain.money import Money
from vinayak.schema import pulse as P

logger = logging.getLogger(__name__)

# How many chases one card's button may queue in a single press.
MAX_CHASES_PER_CARD = 3

# Which cards each role leads with. Same catalogue, different first screen —
# a user can pin their own order, which overrides this.
ROLE_ORDER: dict[str, list[str]] = {
    "owner":      ["week_delta", "cash_30d", "aging_drift", "reorder_radar", "anomalies",
                   "concentration", "trapped_capital", "payment_behaviour", "working_capital"],
    "finance":    ["working_capital", "aging_drift", "payment_behaviour", "cash_30d",
                   "anomalies", "week_delta", "trapped_capital", "reorder_radar", "concentration"],
    "accountant": ["anomalies", "aging_drift", "working_capital", "cash_30d",
                   "payment_behaviour", "week_delta", "trapped_capital", "concentration", "reorder_radar"],
    "sales":      ["reorder_radar", "week_delta", "concentration", "payment_behaviour",
                   "cash_30d", "aging_drift", "trapped_capital", "anomalies", "working_capital"],
    "viewer":     ["week_delta", "cash_30d", "aging_drift", "concentration",
                   "reorder_radar", "trapped_capital", "anomalies", "payment_behaviour", "working_capital"],
}
DEFAULT_ORDER = ROLE_ORDER["owner"]


def _card(key, title, headline, *, display=None, change=None, change_display=None,
          direction=None, change_label=None, why="", items=None, action=None,
          confidence=P.CERTAIN, severity=0, data=None) -> dict:
    return {
        "key": key, "title": title,
        "headline": {"value": headline, "display": display if display is not None else str(headline)},
        "change": None if change is None else {
            "value": change, "display": change_display, "direction": direction,
            "label": change_label or "vs your usual"},
        "why": why, "items": items or [], "action": action,
        "confidence": confidence, "severity": int(severity),
        "stale": bool((data or {}).get("stale")),
        "last_synced_at": (data or {}).get("last_synced_at"),
    }


def _dir(v: float, good_when_negative: bool = False) -> str:
    if abs(v) < 1e-9:
        return "flat"
    up = v > 0
    if good_when_negative:
        return "bad" if up else "good"
    return "good" if up else "bad"


def _names(rows: list[dict], key: str = "customer_name", n: int = 2) -> str:
    got = [r.get(key) for r in rows[:n] if r.get(key)]
    if not got:
        return ""
    return got[0] if len(got) == 1 else " and ".join([", ".join(got[:-1]), got[-1]])


# ── the eight (plus one) cards ────────────────────────────────────────────────

def card_aging_drift(d: dict) -> dict:
    if d.get("history_building"):
        return _card("aging_drift", "Aging drift", 0, display="—",
                     why=f"Recording the receivables book daily; drift needs about a week of history "
                         f"({d.get('history_days', 0)} days so far).",
                     confidence=P.UNCERTAIN, severity=5, data=d)
    drift, movers = d["drift"], d.get("movers", [])
    worst = f" — mostly {_names(movers)}" if movers else ""
    if abs(drift) < 1:
        why = f"Nothing moved into the 61–90 and 90+ buckets in {d['window_days']} days."
    else:
        why = (f"{Money.compact(abs(drift))} {'moved into' if drift > 0 else 'came out of'} the 61–90 "
               f"and 90+ buckets in {d['window_days']} days{worst}.")
    sev = 20 + min(70, abs(d["drift_pct"]) * 6) if drift > 0 else 10
    return _card("aging_drift", "Aging drift",
                 d["bad_now"], display=Money.compact(d["bad_now"]),
                 change=drift, change_display=f"{'+' if drift > 0 else ''}{Money.compact(drift)}",
                 direction=_dir(drift, good_when_negative=True),
                 change_label=f"in {d['window_days']} days",
                 why=why,
                 items=[{"label": m["customer_name"], "value": Money.compact(m["delta"]),
                         "entity_ref": f"customer:{m['customer_name']}"} for m in movers[:3]],
                 # The label counts what the action will actually do. It used to
                 # say len(movers) while sending only three, which is the kind of
                 # small lie that stops a person trusting the button.
                 action=({"label": f"Draft chases ({len(movers[:MAX_CHASES_PER_CARD])})",
                          "kind": "draft_chase",
                          "params": {"customers": [m["customer_name"]
                                                   for m in movers[:MAX_CHASES_PER_CARD]]}}
                         if movers else None),
                 confidence=P.CERTAIN, severity=sev, data=d)


def card_payment_behaviour(d: dict) -> dict:
    v2 = d.get("basis") == "days_to_pay"
    rows = d.get("worsened") if v2 else d.get("items")
    rows = rows or []
    if not rows:
        return _card("payment_behaviour", "Payment behaviour", 0, display="—",
                     why="No customer is stretching materially right now.",
                     confidence=P.CERTAIN, severity=5, data=d)
    if v2:
        top = rows[0]
        why = (f"{top['customer_name']} is paying {top['days_slower']} days slower than before "
               f"({top['avg_before']} → {top['avg_now']} days).")
        headline, display = top["days_slower"], f"+{top['days_slower']} days"
        conf = P.CERTAIN
    else:
        top = rows[0]
        hist = d.get("payment_history_days", 0)
        note = ("Ranked on the current book; payment dates need about "
                f"{max(1, 14 - hist)} more days of history."
                if hist < 14 else
                "Ranked on the current book — not enough repeat payments yet to compare days-to-pay.")
        why = (f"{top['customer_name']} holds {Money.compact(top['overdue'])} overdue, oldest "
               f"{top['oldest_days_overdue']} days. {note}")
        headline, display = top["overdue"], Money.compact(top["overdue"])
        conf = P.PROBABLE
    return _card("payment_behaviour", "Payment behaviour",
                 headline, display=display, why=why,
                 items=[{"label": r["customer_name"],
                         "value": (f"+{r['days_slower']}d" if v2 else Money.compact(r["overdue"])),
                         "entity_ref": f"customer:{r['customer_name']}"} for r in rows[:3]],
                 action={"label": "Review credit", "kind": "open", "params": {"path": "/dashboard/customers"}},
                 confidence=conf, severity=45 if v2 else 35, data=d)


def card_cash_30d(d: dict) -> dict:
    net = d["net"]
    why = (f"{Money.compact(d['inflow_due'])} falls due in {d['horizon_days']} days, plus about "
           f"{Money.compact(d['inflow_expected_from_overdue'])} of the {Money.compact(d['overdue_total'])} "
           f"overdue if half of it lands; {Money.compact(d['outflow'])} is committed on "
           f"{d['open_po_count']} open POs.")
    return _card("cash_30d", f"Next {d['horizon_days']} days of cash",
                 net, display=Money.compact(net),
                 change=net, change_display=("surplus" if net >= 0 else "shortfall"),
                 direction="good" if net >= 0 else "bad", change_label="in vs out",
                 why=why,
                 items=[{"label": "Due in", "value": Money.compact(d["inflow_due"])},
                        {"label": "Expected from overdue", "value": Money.compact(d["inflow_expected_from_overdue"])},
                        {"label": "Committed out", "value": Money.compact(-d["outflow"])}],
                 action=({"label": "Chase what's overdue", "kind": "open",
                          "params": {"path": "/dashboard/money-in"}} if d["overdue_total"] > 0 else None),
                 # The overdue-collection half is an assumption, not a computed figure.
                 confidence=P.PROBABLE, severity=(75 if net < 0 else 25), data=d)


def card_week_delta(d: dict) -> dict:
    if d.get("no_data"):
        return _card("week_delta", "What changed this week", 0, display="—",
                     why="No sales data synced yet.", confidence=P.UNCERTAIN, severity=0, data=d)
    delta, pct = d["delta"], d["delta_pct"]
    movers = [c for c in d.get("contributors", []) if abs(c["contribution"]) > 0]
    if movers:
        m = movers[0]
        who = (f"mostly {m['customer_name']} "
               f"({'up' if m['contribution'] > 0 else 'down'} {Money.compact(abs(m['contribution']))})")
    else:
        who = "spread across customers"
    why = (f"{Money.compact(d['this_week'])} in the week to {d['week_to']}, "
           f"{abs(pct)}% {'above' if delta >= 0 else 'below'} your usual "
           f"{Money.compact(d['usual_week'])} — {who}.")
    return _card("week_delta", "What changed this week",
                 d["this_week"], display=Money.compact(d["this_week"]),
                 change=delta, change_display=f"{'+' if delta >= 0 else ''}{pct}%",
                 direction=_dir(delta), change_label=f"vs {d['weeks_baseline']}-week usual",
                 why=why,
                 items=[{"label": c["customer_name"],
                         "value": f"{'+' if c['contribution'] >= 0 else ''}{Money.compact(c['contribution'])}",
                         "entity_ref": f"customer:{c['customer_name']}"} for c in movers[:3]],
                 action={"label": "Ask why", "kind": "ask",
                         "params": {"question": "Why did sales change this week?"}},
                 confidence=P.CERTAIN, severity=(55 if pct <= -10 else 20), data=d)


def card_reorder_radar(d: dict) -> dict:
    items = d.get("items", [])
    if not items:
        return _card("reorder_radar", "Regulars overdue to order", 0, display="0",
                     why="Every regular buyer is inside their usual rhythm.",
                     confidence=P.CERTAIN, severity=5, data=d)
    top = items[0]
    why = (f"{len(items)} regular {'customer is' if len(items) == 1 else 'customers are'} past their own "
           f"usual gap — {top['customer_name']} last ordered {top['days_since_last']} days ago against a "
           f"{top['median_gap_days']}-day rhythm. About {Money.compact(d['value_at_stake'])} of typical orders.")
    return _card("reorder_radar", "Regulars overdue to order",
                 len(items), display=str(len(items)),
                 change=d["value_at_stake"], change_display=Money.compact(d["value_at_stake"]),
                 direction="bad", change_label="typical order value at stake",
                 why=why,
                 items=[{"label": i["customer_name"],
                         "value": f"{i['days_since_last']}d / {i['median_gap_days']}d",
                         "entity_ref": f"customer:{i['customer_name']}"} for i in items[:3]],
                 action={"label": f"Draft nudges ({len(items[:5])})", "kind": "draft_nudge",
                         "params": {"customers": [i["customer_name"] for i in items[:5]],
                                    # Named here so the experiment this logs can
                                    # be closed automatically three weeks later.
                                    "metric_key": "customer.days_quiet",
                                    "entity_ref": f"customer:{items[0]['customer_name']}",
                                    "window_days": 21}},
                 confidence=P.CERTAIN, severity=40 + min(30, len(items) * 3), data=d)


def card_concentration(d: dict) -> dict:
    ch = d["top3_change"]
    why = (f"Your top 3 customers are {d['top3_pct']}% of the last {d['window_days']} days' revenue "
           f"({'up' if ch > 0 else 'down' if ch < 0 else 'flat'} {abs(ch)} points on the previous "
           f"{d['window_days']}); {d.get('top_customer') or 'the largest'} alone is {d['top1_pct']}%.")
    return _card("concentration", "Customer concentration",
                 d["top3_pct"], display=f"{d['top3_pct']}%",
                 change=ch, change_display=f"{'+' if ch > 0 else ''}{ch} pts",
                 direction=_dir(ch, good_when_negative=True),
                 change_label=f"vs prior {d['window_days']} days",
                 why=why,
                 items=[{"label": "Top customer", "value": f"{d['top1_pct']}%"},
                        {"label": "Top 3", "value": f"{d['top3_pct']}%"}],
                 action=None, confidence=P.CERTAIN,
                 severity=(45 if d["top3_pct"] > 60 or ch > 5 else 15), data=d)


def card_trapped_capital(d: dict) -> dict:
    delta = d["delta"]
    moved = (f"{'up' if delta > 0 else 'down'} {Money.compact(abs(delta))} "
             f"on {d['compare_days']} days ago" if abs(delta) >= 1
             else f"unchanged over {d['compare_days']} days")
    n = d["dead_count"]
    why = (f"{Money.compact(d['dead_value'])} sits in {n} SKU{'s' if n != 1 else ''} with no sale in "
           f"{d['since_days']} days — {moved}.")
    return _card("trapped_capital", "Trapped capital",
                 d["dead_value"], display=Money.compact(d["dead_value"]),
                 change=delta if abs(delta) >= 1 else None,
                 change_display=f"{'+' if delta > 0 else ''}{Money.compact(delta)}",
                 direction=_dir(delta, good_when_negative=True),
                 change_label=f"in {d['compare_days']} days",
                 why=why,
                 items=[{"label": "Dead SKUs", "value": str(d["dead_count"])}],
                 action=({"label": "Plan a clearance", "kind": "experiment",
                          "params": {"title": "Clear dead stock to past buyers of these categories",
                                     "metric_key": "inventory.dead_stock_value",
                                     "window_days": 42}}
                         if d["dead_value"] > 0 else None),
                 confidence=P.CERTAIN, severity=(35 if delta > 0 else 15), data=d)


def card_anomalies(d: dict) -> dict:
    items = d.get("items", [])
    if not items:
        return _card("anomalies", "Anomalies", 0, display="0",
                     why="Nothing out of the ordinary in the data today.",
                     confidence=P.CERTAIN, severity=0)
    # The card says the worst one in full; the rest are listed by name with a
    # figure. Repeating a whole sentence in the item list is what made this
    # card spill over the one next to it.
    rest = [{"label": i["kind"].replace("_", " ").capitalize(),
             "value": _anomaly_measure(i)} for i in items[1:]]
    return _card("anomalies", "Anomalies", len(items), display=str(len(items)),
                 why=items[0]["text"], items=rest,
                 action={"label": "Investigate", "kind": "open",
                         "params": {"path": _anomaly_path(items[0])}},
                 confidence=P.CERTAIN, severity=max(i["severity"] for i in items))


# Where "Investigate" goes depends on what was found — a stale feed is a Sync
# problem, negative stock is a Stock problem, a price rise is a Money-out one.
_ANOMALY_PATH = {
    "data_stale": "/dashboard/sync",
    "negative_stock": "/dashboard/operations",
    "vendor_price_jump": "/dashboard/money-out",
    "outsized_invoice": "/dashboard/money-in",
}


def _anomaly_path(i: dict) -> str:
    return _ANOMALY_PATH.get(i.get("kind", ""), "/dashboard/sync")


def _anomaly_measure(i: dict) -> str:
    """One short figure per anomaly — never the sentence again."""
    if i.get("count"):
        n = int(i["count"])
        return f"{n} item{'s' if n > 1 else ''}"
    if i.get("value"):
        return Money.compact(float(i["value"]))
    return "flagged"


def card_working_capital(d: dict) -> dict:
    why = (f"{Money.compact(d['locked'])} is tied up — {Money.compact(d['inventory'])} in stock and "
           f"{Money.compact(d['receivables'])} with customers. "
           f"{Money.compact(d['open_commitments'])} is committed on open purchase orders.")
    if not d.get("has_true_ap"):
        why += " Vendor bills aren't synced yet, so this is commitments, not true payables."
    return _card("working_capital", "Working capital",
                 d["locked"], display=Money.compact(d["locked"]),
                 why=why,
                 items=[{"label": "Stock", "value": Money.compact(d["inventory"])},
                        {"label": "Receivables", "value": Money.compact(d["receivables"])},
                        {"label": "Open commitments", "value": Money.compact(-d["open_commitments"])}],
                 action=None,
                 confidence=P.CERTAIN if d.get("has_true_ap") else P.PROBABLE,
                 severity=20, data=d)


# ── assembly ──────────────────────────────────────────────────────────────────

_BUILDERS = [
    ("aging_drift",       P.get_aging_drift,          card_aging_drift),
    ("payment_behaviour", P.get_payment_behaviour,    card_payment_behaviour),
    ("cash_30d",          P.get_cash_30d,             card_cash_30d),
    ("week_delta",        P.get_week_delta,           card_week_delta),
    ("reorder_radar",     P.get_reorder_status,       card_reorder_radar),
    ("concentration",     P.get_concentration_trend,  card_concentration),
    ("trapped_capital",   P.get_dead_stock_delta,     card_trapped_capital),
    ("anomalies",         P.get_anomalies,            card_anomalies),
    ("working_capital",   P.get_working_capital,      card_working_capital),
]


def _has_business_data(conn, company_id: str) -> bool:
    """A brand-new workspace has nothing to say yet. Saying "₹0 is tied up" would
    be technically true and completely useless, so the Pulse says it is waiting."""
    with conn.cursor() as cur:
        cur.execute("""SELECT EXISTS (SELECT 1 FROM canon_sales_invoice_flat WHERE company_id=%s)
                          OR EXISTS (SELECT 1 FROM canon_ar_flat WHERE company_id=%s)""",
                    (company_id, company_id))
        return bool(cur.fetchone()[0])


def build_cards(conn, company_id: str, role: str | None = None,
                pinned: list[str] | None = None, sort: str = "role") -> dict:
    """Every card, ordered for the reader. `sort='severity'` puts whatever
    needs attention first (what the brief uses); `sort='role'` keeps the
    role's familiar order with anything urgent lifted to the top."""
    if not _has_business_data(conn, company_id):
        return {"cards": [_card(
                    "waiting_for_data", "Waiting for your first sync", 0, display="—",
                    why="Connect a data source and run the first sync; the Pulse fills in as "
                        "pages land, and the daily brief starts the next morning.",
                    action={"label": "Connect a source", "kind": "open",
                            "params": {"path": "/dashboard/settings"}},
                    confidence=P.UNCERTAIN, severity=0)],
                "role": role, "failed": [], "needs_attention": 0, "no_data": True}

    cards: list[dict] = []
    failed: list[str] = []
    for key, query_fn, card_fn in _BUILDERS:
        try:
            cards.append(card_fn(query_fn(conn, company_id)))
        except Exception as exc:  # noqa: BLE001 — one bad card must not empty the page
            logger.warning("pulse card %s failed for %s: %s", key, company_id, exc)
            failed.append(key)

    order = pinned or ROLE_ORDER.get(role or "", DEFAULT_ORDER)
    rank = {k: i for i, k in enumerate(order)}
    if sort == "severity":
        cards.sort(key=lambda c: (-c["severity"], rank.get(c["key"], 99)))
    else:
        # Role order, but anything genuinely urgent (≥ 60) floats to the top.
        cards.sort(key=lambda c: (0 if c["severity"] >= 60 else 1,
                                  -c["severity"] if c["severity"] >= 60 else 0,
                                  rank.get(c["key"], 99)))
    return {"cards": cards, "role": role, "failed": failed, "no_data": False,
            "needs_attention": sum(1 for c in cards if c["severity"] >= 60)}
