"""
domain/money.py
────────────────
The single home for Indian-currency formatting and the money-token normaliser
the numeric guard depends on. Previously the formatting logic existed twice —
engine.inr() and tools/read_tools._display() — with subtly different output.
Both now delegate here.

Per the agreed style: a class for the (stateless but cohesive) Money formatter,
and plain module functions for the pure tokenisers used by the safety spine.
"""
from __future__ import annotations

import re

# Every money token (₹… or a number with a lakh/crore/k suffix) must trace to a
# figure the brain computed. Percentages/counts/dates are not money tokens.
_MONEY_RE = re.compile(
    r"₹\s?\d[\d.,]*\s?(?:cr|crore|crores|lakh|lakhs|l|k)?"
    r"|\b\d[\d.,]*\s?(?:cr|crore|crores|lakh|lakhs|l|k)\b",
    re.IGNORECASE,
)


class Money:
    """Indian-currency formatting. Two presentation styles, one implementation:

      • compact — '₹2.50L', '₹3.00Cr', '₹1.5K', '₹-2.50L'  (dashboards, engine)
      • spaced  — '₹2.40 Cr', '-₹99,999'                    (tool evidence)
    """

    @staticmethod
    def compact(n: float | int | None) -> str:
        if n is None:
            return "—"
        n = float(n)
        if abs(n) >= 1e7:
            return f"₹{n / 1e7:.2f}Cr"
        if abs(n) >= 1e5:
            return f"₹{n / 1e5:.2f}L"
        if abs(n) >= 1e3:
            return f"₹{n / 1e3:.1f}K"
        return f"₹{n:.0f}"

    @staticmethod
    def spaced(value: float | int | None) -> str:
        if value is None:
            return "—"
        v = float(value)
        a = abs(v)
        sign = "-" if v < 0 else ""
        if a >= 1e7:
            return f"{sign}₹{a / 1e7:.2f} Cr"
        if a >= 1e5:
            return f"{sign}₹{a / 1e5:.2f} L"
        return f"{sign}₹{a:,.0f}"


def norm_num(tok: str) -> str:
    """Canonicalise a money token so phrasing differences ('2.40 Cr' vs '2.4 Cr',
    a trailing sentence period) don't look like different numbers, while genuinely
    different values stay distinct."""
    t = tok.lower().replace("₹", "").replace(",", "").replace(" ", "")
    t = t.rstrip(".")   # a sentence period the money regex greedily swallowed
    t = (t.replace("crores", "cr").replace("crore", "cr")
          .replace("lakhs", "l").replace("lakh", "l"))
    m = re.match(r"(\d+(?:\.\d+)?)(.*)$", t)
    if m:
        num, suffix = m.group(1), m.group(2)
        if "." in num:
            num = num.rstrip("0").rstrip(".")
        t = num + suffix
    return t


def num_tokens(s: str) -> set[str]:
    """The set of normalised money tokens present in a string."""
    return {norm_num(m.group(0)) for m in _MONEY_RE.finditer(s or "")}
