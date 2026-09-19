"""
contacts_import.py
───────────────────
Where to reach a customer, from the spreadsheet the accountant already has.

A reminder can only go to a customer with an email in `customer_contacts`, and
until now that table filled one customer at a time or from Zoho. Most of our
companies are not on Zoho; what they have is a Tally ledger export or a sheet
someone keeps on the office PC. This module turns that sheet into contacts in
two steps, and the gap between them is the point:

  **preview** — read the file, match every row to a customer we actually chase,
  and say plainly what would happen: which rows matched exactly, which matched
  only after ignoring "Pvt Ltd" (and to whom), which match nobody, which match
  two customers, which are broken, which repeat, and which would replace an
  email already on file. Nothing is written.

  **commit** — write only the rows a person ticked.

Two rules the matcher will not bend:

**It never guesses.** "Sharma Traders" against both "Sharma Traders Pvt Ltd"
and "Sharma Traders LLP" is reported as ambiguous with both names, not
resolved by string distance. A wrong email is worse than no email: the reminder
still goes out, to someone else's customer, with our balance in it.

**It never blanks.** An empty cell means "this sheet doesn't know", not "delete
what we have". A row with a phone and no email leaves the email on file alone.

Customers are keyed by `canon_ar_flat.customer_name` — the same string the
chase list, the ladder, promises and the Inbox use — so an imported contact
lands exactly where the next reminder looks for it.

Everything that decides is a pure function; the stored half is at the bottom.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

# A sheet bigger than this is not a contact list, it is a mistake — most
# likely the invoice register picked from the wrong folder.
MAX_BYTES = 2_000_000
MAX_ROWS = 5_000

# How far down a file the header may sit. Tally and Excel exports put the
# company name, the report title and a date range above the real header.
HEADER_SEARCH_ROWS = 15


class UnreadableFile(ValueError):
    """The file cannot be read as a contact list at all. The message is shown
    to the accountant as-is, so it says what to fix."""


# ── Reading the file ──────────────────────────────────────────────────────
def _decode(data: bytes | str) -> str:
    """Excel on Windows saves "CSV" as cp1252 unless asked otherwise, and
    "CSV UTF-8" with a byte-order mark. Both are common in the same office."""
    if isinstance(data, str):
        return data.lstrip(chr(0xFEFF))
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


# Preference among phone columns, best first: a mobile can receive WhatsApp,
# which is where reminders are going next; an office landline cannot.
_PHONE_PREF = (("whatsapp",), ("mobile", "cell", "cellphone"),
               ("phone", "telephone", "tel", "landline"))
# A name column that names the business beats a bare "Name", which beats the
# name of the person to ask for — Zoho exports carry all three.
_BUSINESS_WORDS = {"customer", "party", "ledger", "client", "buyer", "company",
                   "account", "display", "firm", "business", "debtor"}
_NOT_A_NAME = {"code", "id", "no", "number", "gst", "gstin", "pan", "group",
               "type", "address", "city", "state", "balance", "email", "phone"}


def classify_header(h: str) -> tuple[str, int] | None:
    """What a column holds, as (role, preference; lower is better) — or None
    if we don't use it.

    Tolerant on purpose: "E-mail ID", "Party Name", "Mobile No.",
    "WhatsApp Number" are all the same idea written by different people.
    Strict about what is *not* a match: "Mailing Address" is not an email,
    "Customer Code" is not a name, "Hotel" does not contain a telephone.
    """
    words = re.findall(r"[a-z0-9]+", (h or "").casefold())
    if not words:
        return None
    joined = "".join(words)
    ws = set(words)

    if "email" in joined or ws & {"mail", "mailid"} or (
            "e" in ws and "mail" in ws):
        return ("email", 0)
    for pref, hints in enumerate(_PHONE_PREF):
        if ws & set(hints) or any(joined.startswith(x) for x in hints if len(x) > 3):
            return ("phone", pref)
    if "contact" in ws and ws & {"no", "number", "num"}:
        return ("phone", 2)

    if ws & _NOT_A_NAME:
        return None
    if ws & {"contact", "person"}:
        return ("name", 2) if "name" in ws else None
    if ws & _BUSINESS_WORDS:
        return ("name", 0)
    if "name" in ws or "particulars" in ws:
        return ("name", 1)
    return None


@dataclass
class Columns:
    name: int
    email: int | None
    phones: list[int]            # best first


def find_columns(header: list[str]) -> Columns | None:
    """The column layout of a header row, or None if this row isn't one.

    A header needs a name column and at least one way to reach someone —
    otherwise there is nothing to import.
    """
    names: list[tuple[int, int]] = []
    email = None
    phones: list[tuple[int, int]] = []
    for i, h in enumerate(header):
        c = classify_header(h)
        if not c:
            continue
        role, pref = c
        if role == "name":
            names.append((pref, i))
        elif role == "email" and email is None:
            email = i
        elif role == "phone":
            phones.append((pref, i))
    if not names or (email is None and not phones):
        return None
    return Columns(min(names)[1], email, [i for _, i in sorted(phones)])


@dataclass
class RawRow:
    line: int                    # 1-based line in the file, for "look at row 14"
    name: str
    email: str
    phones: list[str]


def read_rows(data: bytes | str) -> list[RawRow]:
    """The file as rows of (name, email, phones). Raises UnreadableFile with a
    sentence the accountant can act on when the file cannot be used."""
    if isinstance(data, (bytes, bytearray)) and len(data) > MAX_BYTES:
        raise UnreadableFile("That file is too large for a contact list (limit 2 MB).")
    text = _decode(data)
    if len(text.encode("utf-8", errors="ignore")) > MAX_BYTES:
        raise UnreadableFile("That file is too large for a contact list (limit 2 MB).")
    if not text.strip():
        raise UnreadableFile("The file is empty.")

    # Try each separator and keep the first under which a header appears.
    # csv.Sniffer guesses from character counts and is fooled by a sheet whose
    # email cells hold "a@x.in; b@x.in"; a header that parses is not fooled.
    cols = None
    table: list[list[str]] = []
    header_at = 0
    for delim in (",", ";", "\t", "|"):
        table = list(csv.reader(io.StringIO(text), delimiter=delim))
        for idx, row in enumerate(table[:HEADER_SEARCH_ROWS]):
            cols = find_columns(row)
            if cols:
                header_at = idx
                break
        if cols:
            break
    if cols is None:
        raise UnreadableFile(
            "Couldn't find the columns. The file needs a header row with the "
            "customer's name (Name, Customer or Party) and an Email or "
            "Phone/Mobile column.")

    def cell(row: list[str], i: int | None) -> str:
        return row[i].strip() if i is not None and i < len(row) else ""

    out: list[RawRow] = []
    for idx, row in enumerate(table[header_at + 1:], start=header_at + 2):
        if not any((c or "").strip() for c in row):
            continue
        out.append(RawRow(line=idx, name=cell(row, cols.name),
                          email=cell(row, cols.email),
                          phones=[cell(row, i) for i in cols.phones]))
        if len(out) > MAX_ROWS:
            raise UnreadableFile(f"More than {MAX_ROWS:,} rows — split the file.")
    return out


# ── Cleaning a value ──────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"^[a-z0-9._%+'-]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$")


def normalise_email(raw: str | None) -> tuple[str | None, str | None]:
    """(email, problem). Empty in, (None, None) out — blank is not an error.

    A cell with two addresses ("accounts@x.in; owner@x.in") takes the first:
    the accounts address is conventionally listed first, and one good
    recipient beats rejecting the row.
    """
    s = (raw or "").strip()
    if not s:
        return None, None
    s = re.sub(r"^mailto:", "", s, flags=re.I)
    first = re.split(r"[;,/\s]+", s)[0].strip().strip("<>").casefold()
    if _EMAIL_RE.match(first) and ".." not in first:
        return first, None
    return None, f"'{raw.strip()}' is not an email address"


def _sci_to_digits(s: str) -> str:
    """Excel shows a long number as 9.19876E+11 and saves it that way.
    Recover the digits when the precision survived; otherwise leave it for
    the validator to reject rather than invent digits."""
    if re.fullmatch(r"\d(\.\d+)?[eE]\+?\d+", s):
        try:
            return str(int(Decimal(s)))
        except (InvalidOperation, ValueError):
            return s
    return s


def normalise_phone(raw: str | None) -> tuple[str | None, str | None]:
    """(E.164 phone, problem) for an Indian business contact list.

    Handles what these sheets actually contain: "98765 43210", "+91-98765-43210",
    "09876543210", "919876543210", a trailing ".0" from Excel, a landline with
    its STD code ("011-2345 6789"), and two numbers in one cell (the first is
    kept). A number with an explicit non-Indian "+" code is kept as written.
    """
    s = (raw or "").strip()
    if not s:
        return None, None
    first = re.split(r"\s*[/,;]\s*|\s+or\s+", s)[0].strip()
    first = _sci_to_digits(first)
    first = re.sub(r"\.0+$", "", first)
    plus = first.startswith("+") or first.startswith("00")
    digits = re.sub(r"\D", "", first)
    if first.startswith("00"):
        digits = digits[2:]

    def bad() -> tuple[None, str]:
        return None, f"'{s}' is not a phone number we can use"

    if plus:
        if digits.startswith("91"):
            rest = digits[2:]
            return (f"+91{rest}", None) if len(rest) == 10 else bad()
        return (f"+{digits}", None) if 8 <= len(digits) <= 15 else bad()
    if len(digits) == 10:
        # A mobile (6–9…) or a landline written with its STD code but no 0.
        return (f"+91{digits}", None) if digits[0] != "0" else bad()
    if len(digits) == 11 and digits[0] == "0":
        return f"+91{digits[1:]}", None
    if len(digits) == 12 and digits.startswith("91"):
        return f"+{digits}", None
    return bad()


# ── Matching a name to a customer ─────────────────────────────────────────
# Trailing words that say what kind of company it is, not which company.
_LEGAL_SUFFIXES = {"pvt", "private", "ltd", "limited", "llp", "p", "inc",
                   "pl", "opc"}


def name_key(name: str) -> str:
    """The comparable core of a company name.

    "M/s. Sharma & Sons Pvt. Ltd." and "Sharma and Sons Private Limited" are
    one customer written two ways; both become "sharmaandsons". Only legal
    form is dropped — never "Traders", "Industries" or "& Co", which are part
    of how two different businesses tell themselves apart.
    """
    s = (name or "").casefold().strip()
    s = s.replace("&", " and ")
    s = re.sub(r"^\s*(m\s*/\s*s\.?|messrs\.?|m/s)\s*", "", s)
    s = re.sub(r"\(\s*p\s*\)", " p ", s)          # "(P) Ltd"
    tokens = re.findall(r"[a-z0-9]+", s)
    if tokens and tokens[0] in ("ms", "messrs"):
        tokens = tokens[1:]
    while len(tokens) > 1 and tokens[-1] in _LEGAL_SUFFIXES:
        tokens.pop()
    return "".join(tokens)


def _squash(s: str) -> str:
    return " ".join((s or "").split())


@dataclass
class NameIndex:
    exact: dict[str, str]
    by_key: dict[str, list[str]]


def build_index(customer_names) -> NameIndex:
    exact: dict[str, str] = {}
    by_key: dict[str, list[str]] = {}
    for n in customer_names:
        if not n:
            continue
        exact.setdefault(_squash(n), n)
        k = name_key(n)
        if k and n not in by_key.setdefault(k, []):
            by_key[k].append(n)
    for v in by_key.values():
        v.sort()
    return NameIndex(exact, by_key)


@dataclass(frozen=True)
class Match:
    kind: str                    # exact | fuzzy | ambiguous | unmatched
    customer_ref: str | None
    candidates: tuple[str, ...] = ()


def match_name(name: str, index: NameIndex) -> Match:
    """Exact first; then ignoring case, punctuation and legal form; and when
    that loosening finds more than one customer, say so instead of picking."""
    hit = index.exact.get(_squash(name))
    if hit:
        return Match("exact", hit)
    cands = index.by_key.get(name_key(name), [])
    if len(cands) == 1:
        return Match("fuzzy", cands[0])
    if len(cands) > 1:
        return Match("ambiguous", None, tuple(cands))
    return Match("unmatched", None)


# ── The preview ───────────────────────────────────────────────────────────
@dataclass
class PreviewRow:
    line: int
    name: str
    status: str                  # matched | fuzzy | ambiguous | unmatched | invalid | duplicate | unchanged
    customer_ref: str | None = None
    candidates: list[str] = field(default_factory=list)
    email: str | None = None
    phone: str | None = None
    existing_email: str | None = None
    existing_phone: str | None = None
    overwrites: list[str] = field(default_factory=list)   # "email" / "phone"
    problems: list[str] = field(default_factory=list)
    duplicate_of: int | None = None
    include: bool = False        # the suggested tick; the person decides

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def preview(rows: list[RawRow], customer_names, existing: dict[str, dict]) -> dict:
    """What committing this sheet would do, row by row. Writes nothing.

    `existing` is the contact book as {customer_ref: {"email", "phone"}}.

    The suggested tick is on only for rows that are safe without reading:
    a confident match that adds something and replaces nothing. Anything that
    would change an email already on file is shown, unticked, with both
    addresses side by side — overwriting a working address from a stale sheet
    is the one mistake here that silently stops reminders arriving.
    """
    index = build_index(customer_names)
    out: list[PreviewRow] = []
    first_line_for: dict[str, int] = {}

    for r in rows:
        pr = PreviewRow(line=r.line, name=r.name, status="invalid")
        email, eprob = normalise_email(r.email)
        phone = None
        pprobs: list[str] = []
        for p in r.phones:
            ph, prob = normalise_phone(p)
            if ph and not phone:
                phone = ph
            elif prob:
                pprobs.append(prob)
        pr.email, pr.phone = email, phone
        if eprob:
            pr.problems.append(eprob)
        if not phone:
            pr.problems.extend(pprobs)

        if not r.name.strip():
            pr.problems.insert(0, "no customer name")
            out.append(pr)
            continue
        if not email and not phone:
            if not pr.problems:
                pr.problems.append("no email or phone")
            out.append(pr)
            continue

        m = match_name(r.name, index)
        pr.customer_ref = m.customer_ref
        pr.candidates = list(m.candidates)
        if m.kind == "unmatched":
            pr.status = "unmatched"
            out.append(pr)
            continue
        if m.kind == "ambiguous":
            pr.status = "ambiguous"
            out.append(pr)
            continue

        ref = m.customer_ref
        assert ref is not None
        if ref in first_line_for:
            pr.status = "duplicate"
            pr.duplicate_of = first_line_for[ref]
            out.append(pr)
            continue
        first_line_for[ref] = r.line

        have = existing.get(ref) or {}
        pr.existing_email = have.get("email") or None
        pr.existing_phone = have.get("phone") or None
        if email and pr.existing_email and email != pr.existing_email.strip().casefold():
            pr.overwrites.append("email")
        # A phone on file may be in any format ("98765 43210" from Zoho); the
        # same number written differently is not a change.
        on_file_phone = normalise_phone(pr.existing_phone)[0] or pr.existing_phone
        if phone and pr.existing_phone and phone != on_file_phone:
            pr.overwrites.append("phone")

        adds = (email and not pr.existing_email) or (phone and not pr.existing_phone)
        if not adds and not pr.overwrites:
            pr.status = "unchanged"
        else:
            pr.status = "matched" if m.kind == "exact" else "fuzzy"
            pr.include = not pr.overwrites
        out.append(pr)

    counts: dict[str, int] = {}
    for p in out:
        counts[p.status] = counts.get(p.status, 0) + 1
    return {
        "rows": [p.as_dict() for p in out],
        "counts": {s: counts.get(s, 0) for s in
                   ("matched", "fuzzy", "ambiguous", "unmatched", "invalid",
                    "duplicate", "unchanged")},
        "overwrites": sum(1 for p in out if p.overwrites),
        "suggested": sum(1 for p in out if p.include),
        "total": len(out),
    }


# ── The commit ────────────────────────────────────────────────────────────
def plan_commit(rows: list[dict], customer_names) -> tuple[list[dict], list[dict]]:
    """Which confirmed rows may be written, re-checked on the server.

    The browser's preview is not trusted: the customer must be one we know by
    exactly that name, and the values are cleaned again. A blank value becomes
    None, which the upsert treats as "leave what's there" — so a confirmed row
    can add or replace, never erase.
    """
    known = set(n for n in customer_names if n)
    writes: list[dict] = []
    rejected: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        raw_ref = r.get("customer_ref") or ""
        # Names are stored as the source wrote them; allow only whitespace
        # drift at the edges, nothing looser.
        ref = raw_ref if raw_ref in known else raw_ref.strip()
        if ref not in known:
            rejected.append({"customer_ref": ref, "reason": "not a known customer"})
            continue
        if ref in seen:
            rejected.append({"customer_ref": ref, "reason": "listed twice"})
            continue
        email, eprob = normalise_email(r.get("email"))
        phone, pprob = normalise_phone(r.get("phone"))
        if eprob or pprob or (not email and not phone):
            rejected.append({"customer_ref": ref,
                             "reason": eprob or pprob or "nothing to save"})
            continue
        seen.add(ref)
        writes.append({"customer_ref": ref, "email": email, "phone": phone})
    return writes, rejected


# ── Coverage: who can a reminder actually reach? ──────────────────────────
def summarise_coverage(overdue: list[tuple[str, float, int]],
                       contacts: dict[str, dict]) -> dict:
    """Of the customers who owe overdue money, how many we could chase today.

    "Reachable" means an email on file, because email is the only channel a
    reminder is sent on now. A phone-only customer is still listed as
    unreachable — with the phone shown, so someone can call and ask for the
    address — rather than counted as covered and then silently never chased.
    Ranked by outstanding: the template the accountant downloads should start
    with the address worth the most.
    """
    with_email = with_phone = with_either = 0
    unreachable = []
    for name, outstanding, days in overdue:
        c = contacts.get(name) or {}
        e, p = bool(c.get("email")), bool(c.get("phone"))
        with_email += e
        with_phone += p
        with_either += e or p
        if not e:
            unreachable.append({"customer_name": name,
                                "outstanding": round(float(outstanding or 0), 2),
                                "days_overdue": int(days or 0),
                                "phone": c.get("phone") or None})
    unreachable.sort(key=lambda u: u["outstanding"], reverse=True)
    return {
        "overdue_customers": len(overdue),
        "with_email": with_email,
        "with_phone": with_phone,
        "with_either": with_either,
        "unreachable_count": len(unreachable),
        "unreachable_value": round(sum(u["outstanding"] for u in unreachable), 2),
        "unreachable": unreachable,
    }


# ══════════════════════════════════════════════════════════════════════════
# The stored half
# ══════════════════════════════════════════════════════════════════════════

def customer_names(conn, company_id: str) -> list[str]:
    """Every customer name the receivables book knows — the key reminders use.
    Settled customers are included: a contact saved today is still right when
    they next fall behind."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT DISTINCT customer_name FROM canon_ar_flat
                WHERE company_id = %s AND customer_name IS NOT NULL
                  AND customer_name <> ''""", (company_id,))
        return [r[0] for r in cur.fetchall()]


def existing_contacts(conn, company_id: str) -> dict[str, dict]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT customer_ref, email, phone, source FROM customer_contacts
                WHERE company_id = %s""", (company_id,))
        return {r[0]: {"email": r[1], "phone": r[2], "source": r[3]}
                for r in cur.fetchall()}


def overdue_customers(conn, company_id: str) -> list[tuple[str, float, int]]:
    """Same definition of overdue as the chase list, so the two screens agree
    on how many customers there are."""
    with conn.cursor() as cur:
        cur.execute(
            """SELECT customer_name,
                      COALESCE(SUM(outstanding_amount), 0),
                      MAX(CURRENT_DATE - due_date)
                 FROM canon_ar_flat
                WHERE company_id = %s AND COALESCE(outstanding_amount, 0) > 0
                  AND due_date IS NOT NULL AND due_date < CURRENT_DATE
                GROUP BY customer_name""", (company_id,))
        return [(r[0], float(r[1] or 0), int(r[2] or 0)) for r in cur.fetchall()]


def coverage(conn, company_id: str) -> dict:
    return summarise_coverage(overdue_customers(conn, company_id),
                              existing_contacts(conn, company_id))
