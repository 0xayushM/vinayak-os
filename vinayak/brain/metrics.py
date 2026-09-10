"""
brain/metrics.py
─────────────────
The small set of numbers an experiment can be judged on.

An experiment is only real if somebody can say afterwards whether it worked,
and that is only true if the metric was chosen BEFORE it ran and can be read
the same way twice. So the metric is a key from this table — not a sentence —
and reading it is a query, never an interpretation.

Every metric declares its direction, because "went down" is good news for
overdue money and bad news for revenue, and nothing else in the system can
work that out on its own.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str                 # 'inr' | 'days' | 'pct' | 'count'
    lower_is_better: bool
    read: Callable            # (conn, company_id, entity_ref) -> float | None


def _overdue_total(conn, company_id, _entity=None) -> float | None:
    with conn.cursor() as cur:
        cur.execute("""SELECT COALESCE(SUM(outstanding_amount),0) FROM canon_ar_flat
                        WHERE company_id=%s AND COALESCE(outstanding_amount,0)>0
                          AND due_date < CURRENT_DATE""", (company_id,))
        return float(cur.fetchone()[0] or 0)


def _bucket_60plus(conn, company_id, _entity=None) -> float | None:
    with conn.cursor() as cur:
        cur.execute("""SELECT COALESCE(SUM(outstanding_amount),0) FROM canon_ar_flat
                        WHERE company_id=%s AND COALESCE(outstanding_amount,0)>0
                          AND (CURRENT_DATE - due_date) > 60""", (company_id,))
        return float(cur.fetchone()[0] or 0)


def _customer_outstanding(conn, company_id, entity_ref) -> float | None:
    name = _name_from(entity_ref)
    if not name:
        return None
    with conn.cursor() as cur:
        cur.execute("""SELECT COALESCE(SUM(outstanding_amount),0) FROM canon_ar_flat
                        WHERE company_id=%s AND customer_name=%s""", (company_id, name))
        return float(cur.fetchone()[0] or 0)


def _avg_days_to_pay(conn, company_id, _entity=None) -> float | None:
    from vinayak.schema.pulse import get_inferred_payments
    d = get_inferred_payments(conn, company_id, window_days=120)
    return d.get("avg_days_to_pay")


def _customer_days_quiet(conn, company_id, entity_ref) -> float | None:
    """Days since this customer last bought. The outcome metric for a nudge:
    if they ordered, this collapses to a small number."""
    name = _name_from(entity_ref)
    if not name:
        return None
    with conn.cursor() as cur:
        cur.execute("""SELECT MAX(invoice_date) FROM canon_sales_invoice_flat
                        WHERE company_id=%s AND customer_name=%s""", (company_id, name))
        row = cur.fetchone()
    if not row or not row[0]:
        return None
    from datetime import date
    return float((date.today() - row[0]).days)


def _dead_stock_value(conn, company_id, _entity=None) -> float | None:
    from vinayak.schema.pulse import get_dead_stock_delta
    return get_dead_stock_delta(conn, company_id).get("dead_value")


def _top1_share(conn, company_id, _entity=None) -> float | None:
    from vinayak.schema.pulse import get_concentration_trend
    return get_concentration_trend(conn, company_id).get("top1_pct")


def _name_from(entity_ref: str | None) -> str | None:
    if not entity_ref:
        return None
    return entity_ref.split(":", 1)[1] if ":" in entity_ref else entity_ref


METRICS: dict[str, Metric] = {m.key: m for m in [
    Metric("ar.overdue_total", "Total overdue", "inr", True, _overdue_total),
    Metric("ar.bucket_60plus", "Owed for more than 60 days", "inr", True, _bucket_60plus),
    Metric("ar.avg_days_to_pay", "Average days to pay", "days", True, _avg_days_to_pay),
    Metric("customer.outstanding", "Outstanding from this customer", "inr", True,
           _customer_outstanding),
    Metric("customer.days_quiet", "Days since this customer last bought", "days", True,
           _customer_days_quiet),
    Metric("inventory.dead_stock_value", "Capital in stock nobody has bought", "inr", True,
           _dead_stock_value),
    Metric("revenue.top1_share", "Share of revenue from the largest customer", "pct", True,
           _top1_share),
]}


def read(conn, company_id: str, metric_key: str, entity_ref: str | None = None) -> float | None:
    """Read a metric now. Returns None when it cannot be computed — which is a
    real answer, and becomes an 'inconclusive' outcome rather than a zero."""
    m = METRICS.get(metric_key)
    if m is None:
        return None
    try:
        return m.read(conn, company_id, entity_ref)
    except Exception as exc:  # noqa: BLE001
        logger.warning("metric %s failed for %s: %s", metric_key, company_id, exc)
        return None
