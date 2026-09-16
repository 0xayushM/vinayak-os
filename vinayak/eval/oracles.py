"""
eval/oracles.py
────────────────
Independent ground truth for the facts the engine states.

The engine's answers are only as true as their Evidence — the numeric guard
already forces every rupee in an answer to trace to an Evidence row. So
grading factual accuracy means grading Evidence against a figure computed some
other way, and "some other way" has to mean *genuinely* other: these queries
deliberately do not import anything from `schema/queries.py`. They are written
to be obviously correct rather than efficient or reusable. If an oracle and the
engine ever share a helper, the harness is grading the engine against itself
and the number it produces is worthless.

**What is graded, and what is not.** Only facts with a window-free definition.
"Total outstanding" is unambiguous — every unpaid invoice, today. "Revenue" is
not: it depends on a period the engine picks, and an oracle that re-derived
that period would be copying the thing it is meant to check. Grading the
unambiguous facts gives a real number for a real subset; pretending to grade
the ambiguous ones would give a bigger number that means less.

Identity oracles (who is the largest debtor, which SKU sells most) are graded
too, and are robust in a way the amounts are not: the top customer is the same
customer over any sensible window.
"""
from __future__ import annotations

# Numbers are floats out of Postgres; this is the wobble we allow before
# calling an Evidence figure wrong. Half a percent is far tighter than any
# real error and loose enough for rounding.
DEFAULT_TOLERANCE_PCT = 0.5


def _one(conn, sql: str, params: tuple):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
    return row[0] if row else None


# ── money owed to us ──────────────────────────────────────────────────────
def ar_outstanding(conn, company_id: str):
    return float(_one(conn, """SELECT COALESCE(SUM(outstanding_amount),0)
                                 FROM canon_ar_flat WHERE company_id=%s""", (company_id,)) or 0)


def ar_overdue(conn, company_id: str):
    return float(_one(conn, """SELECT COALESCE(SUM(outstanding_amount),0)
                                 FROM canon_ar_flat
                                WHERE company_id=%s AND due_date < CURRENT_DATE""",
                      (company_id,)) or 0)


def ar_biggest_debtor(conn, company_id: str):
    return _one(conn, """SELECT customer_name FROM canon_ar_flat
                          WHERE company_id=%s AND COALESCE(outstanding_amount,0) > 0
                          GROUP BY customer_name
                          ORDER BY SUM(outstanding_amount) DESC LIMIT 1""", (company_id,))


def ar_most_overdue_customer(conn, company_id: str):
    return _one(conn, """SELECT customer_name FROM canon_ar_flat
                          WHERE company_id=%s AND due_date < CURRENT_DATE
                            AND COALESCE(outstanding_amount,0) > 0
                          GROUP BY customer_name
                          ORDER BY SUM(outstanding_amount) DESC LIMIT 1""", (company_id,))


# ── stock ─────────────────────────────────────────────────────────────────
def inventory_value(conn, company_id: str):
    return float(_one(conn, """SELECT COALESCE(SUM(total_value),0)
                                 FROM canon_inventory_flat WHERE company_id=%s""",
                      (company_id,)) or 0)


def inventory_sku_count(conn, company_id: str):
    return float(_one(conn, """SELECT COUNT(*) FROM canon_inventory_flat
                                WHERE company_id=%s""", (company_id,)) or 0)


# ── commitments in and out ────────────────────────────────────────────────
def overdue_po_count(conn, company_id: str):
    """Distinct purchase orders past their expected date and not closed.

    Note what this can and cannot check. TranzAct leaves every PO quantity at
    zero, so there is no independent signal for "still outstanding" — the
    oracle can only verify that the engine counts PURCHASE ORDERS rather than
    lines, not that its open-ness rule is right. Saying which half is checked
    is more useful than a check that quietly isn't one. The first version of
    this oracle required a pending quantity, found none, and reported the
    engine wrong; the engine was right and the oracle was measuring a field
    this source does not fill.
    """
    return float(_one(conn, """SELECT COUNT(DISTINCT po_number)
                                 FROM canon_purchase_order_flat
                                WHERE company_id=%s
                                  AND expected_date IS NOT NULL
                                  AND expected_date < CURRENT_DATE
                                  AND LOWER(COALESCE(status,'')) NOT IN
                                      ('received', 'cancelled')""",
                      (company_id,)) or 0)


def overdue_order_count(conn, company_id: str):
    """Distinct sales orders past their delivery date with something still to
    go out. Here `pending_qty` IS populated, so it is the honest test — an
    order with nothing pending has been delivered whatever its status says."""
    return float(_one(conn, """SELECT COUNT(DISTINCT order_number)
                                 FROM canon_sales_order_flat
                                WHERE company_id=%s AND COALESCE(pending_qty,0) > 0
                                  AND LOWER(COALESCE(status,'')) <> 'cancelled'
                                  AND delivery_date IS NOT NULL
                                  AND delivery_date < CURRENT_DATE""", (company_id,)) or 0)


# ── who and what ──────────────────────────────────────────────────────────
def top_customer_1y(conn, company_id: str):
    """The largest customer by invoiced value over a full year — long enough
    that the answer does not depend on where exactly the window starts."""
    return _one(conn, """SELECT customer_name FROM canon_sales_invoice_flat
                          WHERE company_id=%s AND invoice_date >= CURRENT_DATE - 365
                          GROUP BY customer_name
                          ORDER BY SUM(line_total) DESC LIMIT 1""", (company_id,))


def top_sku_1y(conn, company_id: str):
    return _one(conn, """SELECT sku_name FROM canon_sales_invoice_flat
                          WHERE company_id=%s AND invoice_date >= CURRENT_DATE - 365
                            AND sku_name IS NOT NULL
                          GROUP BY sku_name ORDER BY SUM(line_total) DESC LIMIT 1""",
                (company_id,))


def top_vendor_1y(conn, company_id: str):
    return _one(conn, """SELECT vendor_name FROM canon_purchase_invoice_flat
                          WHERE company_id=%s AND invoice_date >= CURRENT_DATE - 365
                          GROUP BY vendor_name ORDER BY SUM(line_total) DESC LIMIT 1""",
                (company_id,))


def ar_over_180(conn, company_id: str):
    """Outstanding more than 180 days past due — the provisioning question."""
    return float(_one(conn, """SELECT COALESCE(SUM(outstanding_amount),0)
                                 FROM canon_ar_flat
                                WHERE company_id=%s AND COALESCE(outstanding_amount,0) > 0
                                  AND due_date IS NOT NULL
                                  AND (CURRENT_DATE - due_date) > 180""", (company_id,)) or 0)


def ar_over_90(conn, company_id: str):
    return float(_one(conn, """SELECT COALESCE(SUM(outstanding_amount),0)
                                 FROM canon_ar_flat
                                WHERE company_id=%s AND COALESCE(outstanding_amount,0) > 0
                                  AND due_date IS NOT NULL
                                  AND (CURRENT_DATE - due_date) > 90""", (company_id,)) or 0)


def related_party_sales_1y(conn, company_id: str):
    """Billed to other connected group companies, matched by name — the same
    limitation as the query itself, stated in both places."""
    rows = None
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM companies WHERE id <> %s AND LENGTH(name) >= 5",
                    (company_id,))
        names = [r[0] for r in cur.fetchall()]
    if not names:
        return None
    return float(_one(conn, """SELECT COALESCE(SUM(line_total),0)
                                 FROM canon_sales_invoice_flat
                                WHERE company_id=%s AND invoice_date >= CURRENT_DATE - 365
                                  AND customer_name ILIKE ANY(%s)""",
                      (company_id, [f"%{n}%" for n in names])) or 0)


def negative_stock_skus(conn, company_id: str):
    """An audit red flag: stock that has gone below zero is a sequence or
    data-entry error, never real."""
    return float(_one(conn, """SELECT COUNT(*) FROM canon_inventory_flat
                                WHERE company_id=%s AND COALESCE(quantity,0) < 0""",
                      (company_id,)) or 0)


ORACLES = {
    "ar_over_180": ar_over_180,
    "ar_over_90": ar_over_90,
    "related_party_sales_1y": related_party_sales_1y,
    "negative_stock_skus": negative_stock_skus,
    "ar_outstanding": ar_outstanding,
    "ar_overdue": ar_overdue,
    "ar_biggest_debtor": ar_biggest_debtor,
    "ar_most_overdue_customer": ar_most_overdue_customer,
    "inventory_value": inventory_value,
    "inventory_sku_count": inventory_sku_count,
    "overdue_po_count": overdue_po_count,
    "overdue_order_count": overdue_order_count,
    "top_customer_1y": top_customer_1y,
    "top_sku_1y": top_sku_1y,
    "top_vendor_1y": top_vendor_1y,
}


def read(conn, company_id: str, name: str):
    """The ground truth, or None when it cannot be computed — which is not a
    failure of the engine and must not be graded as one."""
    fn = ORACLES.get(name)
    if fn is None:
        raise KeyError(f"unknown oracle: {name}")
    try:
        return fn(conn, company_id)
    except Exception:  # noqa: BLE001 — a broken oracle ungrades its case, never fails it
        conn.rollback()
        return None


def matches(truth, value, tolerance_pct: float = DEFAULT_TOLERANCE_PCT) -> bool:
    """Numbers within tolerance; names case-insensitively, either containing
    the other (the engine may show 'DEV COLOUR AND COATINGS PVT LTD' where the
    oracle has the same name with different spacing)."""
    if truth is None or value is None:
        return False
    if isinstance(truth, str):
        a = " ".join(str(truth).lower().split())
        b = " ".join(str(value).lower().split())
        return a in b or b in a
    try:
        t, v = float(truth), float(value)
    except (TypeError, ValueError):
        return False
    if t == 0:
        return abs(v) < 1e-9
    return abs(v - t) / abs(t) * 100 <= tolerance_pct
