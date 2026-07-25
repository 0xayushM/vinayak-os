"""
memory/entity_summary.py
─────────────────────────
The "reason once at ingest" synthesis job. After each sync, we refresh a
pre-built summary per customer from the canonical tables + owner-confirmed memory
facts, so a question about a customer loads one small summary instead of
re-deriving from rows, and the dashboard's customer pages come free.

It also runs a lightweight contradiction check: if the owner told us a customer's
payment terms but their invoices run much later, the summary flags it — the seed
of the "re-ask a stale fact" loop.

Pure builder (`build_customer_summary`) is separated from the DB gather so the
synthesis logic is unit-testable without a database.

    from vinayak.memory.entity_summary import refresh_customer_summaries
    refresh_customer_summaries(conn, company_id)   # called at end of a rebuild
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# How far past stated terms an invoice must run before we call it a contradiction.
_TERMS_GRACE_DAYS = 15


def _inr(v) -> str:
    """Compact Indian-style money label (lakh/crore) for the rendered summary."""
    if v is None:
        return "—"
    v = float(v)
    a = abs(v)
    if a >= 1e7:
        return f"₹{v / 1e7:.2f} Cr"
    if a >= 1e5:
        return f"₹{v / 1e5:.2f} L"
    return f"₹{v:,.0f}"


def build_customer_summary(entity_ref: str, name: str, agg: dict, facts: list[dict]) -> tuple[dict, str]:
    """Assemble one customer's summary + markdown from pre-computed aggregates and
    active memory facts. Pure — no DB. `agg` carries: outstanding, overdue,
    oldest_days_overdue, revenue_total, invoice_count, last_activity."""
    active = [f for f in facts if f.get("status") == "active"]
    fact_view = [{"key": f["claim_key"], "value": f["claim_value"]} for f in active]

    contradictions: list[str] = []
    terms = next((f["claim_value"] for f in active if f["claim_key"] == "payment_terms_days"), None)
    oldest = agg.get("oldest_days_overdue")
    try:
        terms_i = int(terms) if terms is not None else None
    except (TypeError, ValueError):
        terms_i = None
    if terms_i is not None and oldest is not None and oldest > terms_i + _TERMS_GRACE_DAYS:
        contradictions.append(
            f"Stated payment terms {terms_i}d, but has invoices {int(oldest)}d overdue "
            f"— worth re-confirming the terms.")

    summary = {
        "entity_ref": entity_ref,
        "name": name,
        "outstanding": agg.get("outstanding") or 0.0,
        "overdue": agg.get("overdue") or 0.0,
        "oldest_days_overdue": oldest,
        "revenue_total": agg.get("revenue_total") or 0.0,
        "invoice_count": agg.get("invoice_count") or 0,
        "last_activity": agg.get("last_activity"),
        "active_facts": fact_view,
        "contradictions": contradictions,
    }

    lines = [f"# {name or entity_ref}", ""]
    lines.append(f"- Outstanding: {_inr(summary['outstanding'])}"
                 + (f" (overdue {_inr(summary['overdue'])}, oldest {int(oldest)}d)"
                    if summary["overdue"] else ""))
    lines.append(f"- Lifetime revenue: {_inr(summary['revenue_total'])} "
                 f"across {summary['invoice_count']} invoices")
    if summary["last_activity"]:
        lines.append(f"- Last activity: {summary['last_activity']}")
    if fact_view:
        lines.append("- Known facts: " + ", ".join(f"{f['key']}={f['value']}" for f in fact_view))
    if contradictions:
        lines.append("- ⚠ " + " ".join(contradictions))
    return summary, "\n".join(lines)


def _gather(conn, company_id: str) -> tuple[list[tuple], dict, dict, dict]:
    """One-shot DB gather: customers, AR aggregates, revenue aggregates, and
    active facts grouped by entity_ref. Everything keyed on customer_code."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT customer_code, MAX(name) FROM canon_customer "
            "WHERE company_id = %s AND customer_code IS NOT NULL GROUP BY customer_code",
            (company_id,),
        )
        customers = cur.fetchall()

        cur.execute(
            """SELECT customer_code,
                      COALESCE(SUM(outstanding_amount), 0),
                      COALESCE(SUM(outstanding_amount) FILTER (WHERE days_overdue > 0), 0),
                      MAX(days_overdue) FILTER (WHERE days_overdue > 0)
               FROM canon_ar_flat WHERE company_id = %s GROUP BY customer_code""",
            (company_id,),
        )
        ar = {r[0]: (float(r[1] or 0), float(r[2] or 0), r[3]) for r in cur.fetchall()}

        cur.execute(
            """SELECT customer_code,
                      COALESCE(SUM(line_total), 0),
                      COUNT(DISTINCT invoice_number),
                      MAX(invoice_date)
               FROM canon_sales_invoice_flat WHERE company_id = %s GROUP BY customer_code""",
            (company_id,),
        )
        rev = {r[0]: (float(r[1] or 0), int(r[2] or 0), r[3]) for r in cur.fetchall()}

    from vinayak.memory import store as M
    facts_by_ref: dict[str, list] = {}
    for f in M.active_facts(conn, company_id, entity_ref=None):
        facts_by_ref.setdefault(f["entity_ref"], []).append(f)
    return customers, ar, rev, facts_by_ref


def refresh_customer_summaries(conn, company_id: str) -> int:
    """Rebuild entity_summary rows for every customer of a company from canonical
    data + memory. Does NOT commit — the caller's transaction owns the commit."""
    customers, ar, rev, facts_by_ref = _gather(conn, company_id)
    rows = []
    for code, name in customers:
        entity_ref = f"customer:{code}"
        a = ar.get(code, (0.0, 0.0, None))
        r = rev.get(code, (0.0, 0, None))
        agg = {
            "outstanding": a[0], "overdue": a[1], "oldest_days_overdue": a[2],
            "revenue_total": r[0], "invoice_count": r[1],
            "last_activity": r[2].isoformat() if r[2] else None,
        }
        summary, md = build_customer_summary(entity_ref, name, agg, facts_by_ref.get(entity_ref, []))
        rows.append((company_id, "customer", entity_ref, json.dumps(summary), md))

    if not rows:
        return 0
    import psycopg2.extras
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """INSERT INTO entity_summary
                   (company_id, entity_type, entity_ref, summary, rendered_md)
               VALUES %s
               ON CONFLICT (company_id, entity_type, entity_ref)
               DO UPDATE SET summary = EXCLUDED.summary,
                             rendered_md = EXCLUDED.rendered_md,
                             refreshed_at = now()""",
            rows, template="(%s, %s, %s, %s, %s)", page_size=500,
        )
    return len(rows)
