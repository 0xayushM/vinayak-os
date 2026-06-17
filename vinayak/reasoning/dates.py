"""
reasoning/dates.py
───────────────────
Turn the time phrase in a business question into a concrete [start, end] range,
anchored to TODAY (the real current date) — so "last month", "in April",
"since 22 April 2026", "last 30 days", "this quarter" all resolve correctly and
the right slice of data is queried.

parse_period("how much did I sell last month", today=2026-06-10)
    -> {"start": "2026-05-01", "end": "2026-05-31", "label": "in May 2026"}

Returns None when the question has no time phrase (the caller then uses its
default window).
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}
MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_abbr) if m})

_MONTH_RE = "|".join(sorted(MONTHS, key=len, reverse=True))


def _month_range(y: int, m: int) -> tuple[date, date]:
    last = calendar.monthrange(y, m)[1]
    return date(y, m, 1), date(y, m, last)


def _fmt(d: date) -> str:
    return d.isoformat()


def _label(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month and start.day == 1 \
            and end.day == calendar.monthrange(end.year, end.month)[1]:
        return f"in {calendar.month_name[start.month]} {start.year}"
    return f"from {start.strftime('%d %b %Y')} to {end.strftime('%d %b %Y')}"


def _try_date(token: str, today: date) -> date | None:
    token = token.strip().strip(",.")
    # ISO
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", token)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    # dd/mm/yyyy or dd-mm-yyyy
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})$", token)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        y = y + 2000 if y < 100 else y
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    # "22 April 2026" / "22 apr 2026" / "april 22 2026" / "22 april"
    m = re.match(rf"^(\d{{1,2}})\s+({_MONTH_RE})\s*(\d{{4}})?$", token, re.I)
    if m:
        mo = MONTHS[m[2].lower()]
        y = int(m[3]) if m[3] else today.year
        try:
            return date(y, mo, int(m[1]))
        except ValueError:
            return None
    m = re.match(rf"^({_MONTH_RE})\s+(\d{{1,2}})\s*(\d{{4}})?$", token, re.I)
    if m:
        mo = MONTHS[m[1].lower()]
        y = int(m[3]) if m[3] else today.year
        try:
            return date(y, mo, int(m[2]))
        except ValueError:
            return None
    return None


def parse_period(question: str, today: date | None = None) -> dict | None:
    q = question.lower().strip()
    today = today or date.today()

    def out(s: date, e: date, label: str | None = None):
        if s > e:
            s, e = e, s
        return {"start": _fmt(s), "end": _fmt(e), "label": label or _label(s, e)}

    # ── relative keywords ────────────────────────────────────────────────────
    if "today" in q:
        return out(today, today, "today")
    if "yesterday" in q:
        y = today - timedelta(days=1)
        return out(y, y, "yesterday")
    if re.search(r"\bthis month\b|\bmonth to date\b|\bmtd\b", q):
        s, _ = _month_range(today.year, today.month)
        return out(s, today, f"so far in {calendar.month_name[today.month]} {today.year}")
    if re.search(r"\blast month\b|\bprevious month\b|\bpast month\b", q):
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        s, e = _month_range(last_prev.year, last_prev.month)
        return out(s, e)
    if re.search(r"\bthis year\b|\byear to date\b|\bytd\b", q):
        return out(date(today.year, 1, 1), today, f"so far in {today.year}")
    if re.search(r"\blast year\b|\bprevious year\b", q):
        return out(date(today.year - 1, 1, 1), date(today.year - 1, 12, 31), str(today.year - 1))
    if re.search(r"\bthis quarter\b", q):
        qm = 3 * ((today.month - 1) // 3) + 1
        s, _ = _month_range(today.year, qm)
        return out(s, today, "this quarter")
    if re.search(r"\blast quarter\b|\bprevious quarter\b", q):
        qm = 3 * ((today.month - 1) // 3) + 1
        first_q = date(today.year, qm, 1)
        prev_end = first_q - timedelta(days=1)
        pqm = 3 * ((prev_end.month - 1) // 3) + 1
        s, _ = _month_range(prev_end.year, pqm)
        _, e = _month_range(prev_end.year, pqm + 2)
        return out(s, e, "last quarter")
    if re.search(r"\blast week\b|\bpast week\b", q):
        return out(today - timedelta(days=7), today, "in the last 7 days")
    m = re.search(r"\b(?:last|past)\s+(\d{1,3})\s*(day|days|week|weeks|month|months)\b", q)
    if m:
        n = int(m[1]); unit = m[2]
        days = n * (7 if "week" in unit else 30 if "month" in unit else 1)
        return out(today - timedelta(days=days), today, f"in the last {n} {unit}")

    # ── "between X and Y" / "from X to Y" ────────────────────────────────────
    m = re.search(r"(?:between|from)\s+(.+?)\s+(?:and|to|until|till)\s+(.+?)[\?\.]?$", q)
    if m:
        a, b = _try_date(m[1], today), _try_date(m[2], today)
        if a and b:
            return out(a, b)

    # ── "since/from/after <date>" ────────────────────────────────────────────
    m = re.search(r"(?:since|from|after)\s+(.+?)[\?\.]?$", q)
    if m:
        d = _try_date(m[1].split(" and ")[0], today)
        if d:
            return out(d, today, f"since {d.strftime('%d %b %Y')}")

    # ── "in <Month> [year]" ──────────────────────────────────────────────────
    m = re.search(rf"\b(?:in|during|for)\s+({_MONTH_RE})\s*(\d{{4}})?\b", q)
    if m:
        mo = MONTHS[m[1].lower()]
        y = int(m[2]) if m[2] else (today.year if mo <= today.month else today.year - 1)
        s, e = _month_range(y, mo)
        return out(s, e)

    # ── a bare explicit date anywhere → that single day ──────────────────────
    m = re.search(r"\b(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b", q)
    if m:
        d = _try_date(m[1], today)
        if d:
            return out(d, d, d.strftime("%d %b %Y"))

    return None
