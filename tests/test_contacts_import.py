"""
The contacts CSV import — reading the accountant's sheet, matching it to the
customers we chase, and refusing to guess.

A wrong email is worse than no email: the reminder still goes, to the wrong
business, with our balance in it. So most of these tests are about what the
matcher will NOT do.
"""
import pytest

from vinayak.contacts_import import (
    UnreadableFile, build_index, classify_header, match_name, name_key,
    normalise_email, normalise_phone, plan_commit, preview, read_rows,
    summarise_coverage,
)

CUSTOMERS = [
    "Sharma & Sons Pvt Ltd",
    "Gupta Traders",
    "Kapoor Industries Private Limited",
    "Mehta Brothers LLP",
    "Mehta Brothers Pvt. Ltd.",
    "A.B.C. Enterprises",
]


def _preview(csv_text, existing=None, customers=CUSTOMERS):
    return preview(read_rows(csv_text), customers, existing or {})


def _row(result, line):
    return next(r for r in result["rows"] if r["line"] == line)


# ── finding the columns ───────────────────────────────────────────────────
def test_headers_are_recognised_however_they_are_written():
    assert classify_header("Party Name")[0] == "name"
    assert classify_header("Customer")[0] == "name"
    assert classify_header("E-mail ID")[0] == "email"
    assert classify_header("Email Address")[0] == "email"
    assert classify_header("Mobile No.")[0] == "phone"
    assert classify_header("WhatsApp Number")[0] == "phone"
    assert classify_header("Contact Number")[0] == "phone"


def test_things_that_merely_sound_like_a_column_are_not_one():
    assert classify_header("Mailing Address") is None
    assert classify_header("Customer Code") is None
    assert classify_header("GSTIN") is None
    assert classify_header("Hotel") is None


def test_the_header_may_sit_below_a_report_title():
    """Tally puts the company name and a date range above the real header."""
    text = ("Vinayak Industries\nSundry Debtors 1-Apr-26 to 31-Aug-26\n\n"
            "Party Name,Email,Mobile\nGupta Traders,accounts@gupta.in,9876543210\n")
    rows = read_rows(text)
    assert len(rows) == 1 and rows[0].name == "Gupta Traders" and rows[0].line == 5


def test_a_semicolon_separated_file_is_read():
    rows = read_rows("Customer;E-mail\nGupta Traders;a@gupta.in\n")
    assert rows[0].email == "a@gupta.in"


def test_a_utf8_file_with_a_byte_order_mark_is_read():
    rows = read_rows("﻿Name,Email\nGupta Traders,a@gupta.in\n".encode("utf-8"))
    assert rows[0].name == "Gupta Traders"


def test_the_business_name_beats_the_person_to_ask_for():
    rows = read_rows("Contact Name,Company Name,Email\nRavi,Gupta Traders,a@gupta.in\n")
    assert rows[0].name == "Gupta Traders"


def test_a_mobile_is_preferred_to_a_landline_when_both_are_given():
    r = _preview("Name,Phone,Mobile\nGupta Traders,011-23456789,98765 43210\n")
    assert _row(r, 2)["phone"] == "+919876543210"


def test_a_file_without_usable_columns_says_what_it_needs():
    with pytest.raises(UnreadableFile, match="header row"):
        read_rows("Invoice,Amount\nINV-1,5000\n")


def test_an_empty_file_is_refused():
    with pytest.raises(UnreadableFile):
        read_rows(b"   \n")


# ── cleaning values ───────────────────────────────────────────────────────
def test_emails_are_trimmed_and_lowercased():
    assert normalise_email("  Accounts@Gupta.IN ") == ("accounts@gupta.in", None)


def test_a_blank_email_is_not_an_error():
    assert normalise_email("") == (None, None)


@pytest.mark.parametrize("bad", ["gupta.in", "accounts@", "a@b", "a@@b.in",
                                 "a..b@gupta.in", "call ravi"])
def test_bad_emails_are_rejected_with_the_value_shown(bad):
    email, problem = normalise_email(bad)
    assert email is None and "not an email" in problem


def test_two_addresses_in_one_cell_keep_the_first():
    assert normalise_email("accounts@x.in; owner@x.in")[0] == "accounts@x.in"


@pytest.mark.parametrize("raw", ["9876543210", "98765 43210", "+91 98765-43210",
                                 "09876543210", "919876543210", "9876543210.0",
                                 "9.87654321E+09", "0091 9876543210",
                                 "9876543210 / 9811122233"])
def test_indian_mobile_numbers_are_normalised_to_one_form(raw):
    assert normalise_phone(raw) == ("+919876543210", None)


def test_a_landline_with_its_std_code_is_kept():
    assert normalise_phone("011-2345 6789") == ("+911123456789", None)


def test_a_foreign_number_written_with_its_code_is_kept_as_written():
    assert normalise_phone("+971 50 123 4567") == ("+971501234567", None)


@pytest.mark.parametrize("bad", ["12345", "98765432101234567", "N/A", "+91 98765"])
def test_numbers_that_cannot_be_dialled_are_rejected(bad):
    phone, problem = normalise_phone(bad)
    assert phone is None and problem


# ── matching names ────────────────────────────────────────────────────────
def test_legal_form_punctuation_and_ampersand_do_not_change_who_it_is():
    assert name_key("M/s. Sharma & Sons Pvt. Ltd.") == name_key("Sharma and Sons Private Limited")
    assert name_key("Sharma & Sons (P) Ltd") == name_key("SHARMA AND SONS")
    assert name_key("A.B.C. Enterprises") == name_key("ABC Enterprises")


def test_trade_words_that_tell_businesses_apart_are_kept():
    assert name_key("Gupta Traders") != name_key("Gupta Industries")
    assert name_key("Gupta & Co") != name_key("Gupta")


def test_an_exact_name_matches_exactly():
    m = match_name("Gupta Traders", build_index(CUSTOMERS))
    assert m.kind == "exact" and m.customer_ref == "Gupta Traders"


def test_a_loose_name_matches_and_reports_the_name_it_matched():
    m = match_name("M/s Sharma and Sons", build_index(CUSTOMERS))
    assert m.kind == "fuzzy" and m.customer_ref == "Sharma & Sons Pvt Ltd"


def test_a_name_that_fits_two_customers_is_ambiguous_not_guessed():
    m = match_name("Mehta Brothers", build_index(CUSTOMERS))
    assert m.kind == "ambiguous" and m.customer_ref is None
    assert set(m.candidates) == {"Mehta Brothers LLP", "Mehta Brothers Pvt. Ltd."}


def test_an_exact_name_wins_even_when_the_loose_key_is_shared():
    m = match_name("Mehta Brothers LLP", build_index(CUSTOMERS))
    assert m.kind == "exact" and m.customer_ref == "Mehta Brothers LLP"


def test_a_similar_but_different_name_is_unmatched():
    assert match_name("Gupta Trading Co", build_index(CUSTOMERS)).kind == "unmatched"


# ── the preview ───────────────────────────────────────────────────────────
SHEET = """Party Name,Email,Mobile
Gupta Traders,accounts@gupta.in,9876543210
m/s sharma & sons,sharma@sons.in,
Mehta Brothers,mehta@bros.in,
Nobody We Know,x@nobody.in,
Kapoor Industries,not-an-email,
,orphan@x.in,
Gupta Traders,other@gupta.in,
A.B.C. Enterprises,,
"""


def test_every_row_lands_in_exactly_one_bucket():
    r = _preview(SHEET)
    assert r["counts"] == {"matched": 1, "fuzzy": 1, "ambiguous": 1, "unmatched": 1,
                           "invalid": 3, "duplicate": 1, "unchanged": 0}
    assert r["total"] == 8


def test_the_fuzzy_row_shows_who_it_matched():
    row = _row(_preview(SHEET), 3)
    assert row["status"] == "fuzzy" and row["customer_ref"] == "Sharma & Sons Pvt Ltd"


def test_ambiguous_rows_carry_the_candidates_and_are_not_ticked():
    row = _row(_preview(SHEET), 4)
    assert row["status"] == "ambiguous" and len(row["candidates"]) == 2
    assert not row["include"]


def test_a_repeated_customer_points_back_to_its_first_row():
    row = _row(_preview(SHEET), 8)
    assert row["status"] == "duplicate" and row["duplicate_of"] == 2 and not row["include"]


def test_a_row_with_a_bad_email_and_nothing_else_is_invalid():
    row = _row(_preview(SHEET), 6)
    assert row["status"] == "invalid" and "not an email" in row["problems"][0]


def test_a_bad_email_does_not_throw_away_a_good_phone():
    r = _preview("Name,Email,Mobile\nGupta Traders,nope,9876543210\n")
    row = _row(r, 2)
    assert row["status"] == "matched" and row["phone"] == "+919876543210"
    assert row["email"] is None and row["problems"]


def test_a_row_without_a_name_is_invalid():
    assert "no customer name" in _row(_preview(SHEET), 7)["problems"]


def test_replacing_an_email_on_file_is_flagged_and_left_unticked():
    """A stale sheet overwriting a working address silently stops reminders
    arriving. It is shown, never pre-selected."""
    existing = {"Gupta Traders": {"email": "old@gupta.in", "phone": None}}
    row = _row(_preview(SHEET, existing), 2)
    assert row["overwrites"] == ["email"] and row["existing_email"] == "old@gupta.in"
    assert not row["include"]


def test_filling_a_blank_is_ticked_by_default():
    row = _row(_preview(SHEET), 2)
    assert row["status"] == "matched" and row["include"] and not row["overwrites"]


def test_the_same_email_in_a_different_case_is_unchanged_not_an_overwrite():
    existing = {"Gupta Traders": {"email": "Accounts@Gupta.in", "phone": "98765 43210"}}
    row = _row(_preview("Name,Email,Mobile\nGupta Traders,accounts@gupta.in,9876543210\n",
                        existing), 2)
    assert row["status"] == "unchanged" and not row["overwrites"] and not row["include"]


def test_a_phone_only_row_does_not_count_as_replacing_the_email():
    existing = {"Gupta Traders": {"email": "old@gupta.in", "phone": None}}
    row = _row(_preview("Name,Mobile\nGupta Traders,9876543210\n", existing), 2)
    assert row["overwrites"] == [] and row["include"]


# ── the commit ────────────────────────────────────────────────────────────
def test_a_blank_value_is_never_written_over_one_on_file():
    """None reaches the upsert, whose COALESCE keeps what is there."""
    writes, rejected = plan_commit(
        [{"customer_ref": "Gupta Traders", "email": "", "phone": "9876543210"}], CUSTOMERS)
    assert writes == [{"customer_ref": "Gupta Traders", "email": None,
                       "phone": "+919876543210"}]
    assert rejected == []


def test_a_row_with_nothing_to_save_is_rejected():
    writes, rejected = plan_commit(
        [{"customer_ref": "Gupta Traders", "email": " ", "phone": None}], CUSTOMERS)
    assert writes == [] and rejected[0]["reason"] == "nothing to save"


def test_the_commit_refuses_a_customer_we_do_not_know():
    """The browser's preview is not trusted with the key."""
    writes, rejected = plan_commit(
        [{"customer_ref": "gupta traders", "email": "a@gupta.in"}], CUSTOMERS)
    assert writes == [] and rejected[0]["reason"] == "not a known customer"


def test_the_commit_takes_a_customer_once():
    writes, rejected = plan_commit(
        [{"customer_ref": "Gupta Traders", "email": "a@gupta.in"},
         {"customer_ref": "Gupta Traders", "email": "b@gupta.in"}], CUSTOMERS)
    assert [w["email"] for w in writes] == ["a@gupta.in"] and len(rejected) == 1


def test_the_commit_recleans_what_the_browser_sent():
    writes, rejected = plan_commit(
        [{"customer_ref": "Gupta Traders", "email": "not-an-email"}], CUSTOMERS)
    assert writes == [] and "not an email" in rejected[0]["reason"]


# ── coverage ──────────────────────────────────────────────────────────────
def test_coverage_counts_only_email_as_reachable_and_ranks_the_rest_by_money():
    overdue = [("Gupta Traders", 50_000, 40), ("Sharma & Sons Pvt Ltd", 900_000, 10),
               ("Kapoor Industries Private Limited", 200_000, 95)]
    contacts = {"Gupta Traders": {"email": "a@gupta.in", "phone": None},
                "Kapoor Industries Private Limited": {"email": None, "phone": "+919876543210"}}
    c = summarise_coverage(overdue, contacts)
    assert (c["overdue_customers"], c["with_email"], c["with_phone"], c["with_either"]) == (3, 1, 1, 2)
    assert [u["customer_name"] for u in c["unreachable"]] == [
        "Sharma & Sons Pvt Ltd", "Kapoor Industries Private Limited"]
    assert c["unreachable"][1]["phone"] == "+919876543210"
    assert c["unreachable_value"] == 1_100_000
