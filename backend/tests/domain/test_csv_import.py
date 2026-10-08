from datetime import date

import pytest

from app.domain.csv_import import (
    MAX_ROWS,
    CsvImportError,
    fingerprint,
    flag_duplicates,
    parse_csv,
)

SIGNED = """Date,Description,Amount
01/03/2026,GRABFOOD KUALA LUMPUR,-25.90
02/03/2026,Monthly allowance from Parents,"1,000.00"
03/03/2026,TNG toll reload,-10.00
"""


def only(preview):
    return {r.row: r for r in preview.rows}


def test_signed_amounts_decide_the_direction():
    preview = parse_csv(SIGNED)

    rows = only(preview)
    assert [r.type for r in preview.rows] == ["expense", "income", "expense"]
    assert rows[1].amount_sen == 2590
    assert rows[2].amount_sen == 100000  # thousands comma, always positive sen
    assert rows[1].date == date(2026, 3, 1)  # dd/mm/yyyy
    assert preview.skipped == ()
    assert all(r.issues == () for r in preview.rows)


def test_categories_are_guessed_from_the_description():
    rows = only(parse_csv(SIGNED))

    assert rows[1].category_guess == "Food"
    assert rows[2].category_guess == "Allowance"
    assert rows[3].category_guess == "Transport"


def test_separate_debit_and_credit_columns():
    text = "Date,Details,Debit,Credit\n05/03/2026,Mamak dinner,12.50,\n06/03/2026,Gaji,,1500.00\n"

    preview = parse_csv(text)

    assert [(r.type, r.amount_sen) for r in preview.rows] == [("expense", 1250), ("income", 150000)]


@pytest.mark.parametrize(
    ("amount", "sen", "kind"),
    [
        ("RM1,234.50", 123450, "income"),
        ("(25.00)", 2500, "expense"),
        ("-RM 8.90", 890, "expense"),
        ("25.90-", 2590, "expense"),
        ("+40", 4000, "income"),
    ],
)
def test_amount_formats(amount, sen, kind):
    # A negative row is included so the file counts as "signed" and positives are income.
    text = f'Date,Description,Amount\n01/03/2026,Item,"{amount}"\n02/03/2026,Other,-1.00\n'

    first = parse_csv(text).rows[0]

    assert first.amount_sen == sen
    assert first.type == kind


def test_an_unsigned_file_is_assumed_to_be_expenses_unless_the_words_say_income():
    text = (
        "Date,Description,Amount\n01/03/2026,Mamak dinner,12.50\n02/03/2026,Salary March,2000.00\n"
    )

    dinner, salary = parse_csv(text).rows

    assert dinner.type == "expense"
    assert "no sign" in dinner.issues[0]
    assert salary.type == "income"
    assert salary.issues == ()


def test_iso_dates_with_times_and_month_names_parse():
    text = (
        "Date,Description,Amount\n"
        "2026-03-01 10:22:00,A,-1.00\n"
        "2 Mar 2026,B,-1.00\n"
        "03-Mar-2026,C,-1.00\n"
    )

    assert [r.date for r in parse_csv(text).rows] == [
        date(2026, 3, 1),
        date(2026, 3, 2),
        date(2026, 3, 3),
    ]


def test_a_european_decimal_comma_is_rejected_not_guessed():
    text = (
        "\ufefftarikh;keterangan;amaun\n01/03/2026;Makan tengah hari;-9,50\n02/03/2026;Teh;-3.00\n"
    )

    preview = parse_csv(text)

    # "9,50" is ambiguous (decimal comma or thousands?): skipped with a reason, never guessed.
    assert [r.description for r in preview.rows] == ["Teh"]
    assert "amount" in preview.skipped[0].reason


def test_malay_headers_and_semicolons_with_a_valid_amount():
    text = "﻿tarikh;keterangan;amaun\n01/03/2026;Makan tengah hari;-9.50\n"

    (row,) = parse_csv(text).rows

    assert (row.amount_sen, row.type, row.category_guess) == (950, "expense", "Food")


def test_bad_rows_are_reported_with_reasons_never_dropped_silently():
    text = (
        "Date,Description,Amount\n"
        "not a date,Lunch,-5.00\n"
        "01/03/2026,Zero,0.00\n"
        "01/03/2026,Three decimals,-1.234\n"
        "01/03/2026,Missing amount,\n"
        "01/03/2026\n"
        "01/03/2026,Fine,-3.00\n"
    )

    preview = parse_csv(text)

    assert [r.description for r in preview.rows] == ["Fine"]
    reasons = {s.row: s.reason for s in preview.skipped}
    assert "date" in reasons[1]
    assert "zero" in reasons[2] or "missing" in reasons[2]
    assert "amount" in reasons[3]
    assert "missing" in reasons[4] or "zero" in reasons[4]
    assert "columns" in reasons[5]
    assert len(preview.skipped) == 5


def test_row_numbers_count_data_rows_from_one_ignoring_blank_lines():
    text = "Date,Description,Amount\n\n01/03/2026,A,-1.00\n\n02/03/2026,B,-1.00\n"

    assert [r.row for r in parse_csv(text).rows] == [1, 2]


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("", "CSV_NO_ROWS"),
        ("Date,Description,Amount\n", "CSV_NO_ROWS"),
        ("Foo,Bar\n1,2\n", "CSV_MISSING_COLUMNS"),
        ("Description,Amount\nLunch,-5.00\n", "CSV_MISSING_COLUMNS"),
        ("Date,Description\n01/03/2026,Lunch\n", "CSV_MISSING_COLUMNS"),
    ],
)
def test_unusable_files_raise_a_coded_error(text, code):
    with pytest.raises(CsvImportError) as err:
        parse_csv(text)

    assert err.value.code == code
    assert err.value.message


def test_a_file_with_only_bad_rows_is_an_error_not_an_empty_success():
    with pytest.raises(CsvImportError) as err:
        parse_csv("Date,Description,Amount\nnope,Lunch,-5.00\n")

    assert err.value.code == "CSV_NO_ROWS"


def test_too_many_rows_are_refused():
    body = "".join(f"01/03/2026,Item {i},-1.00\n" for i in range(MAX_ROWS + 1))

    with pytest.raises(CsvImportError) as err:
        parse_csv("Date,Description,Amount\n" + body)

    assert err.value.code == "CSV_TOO_MANY_ROWS"


# ---------------------------------------------------------------- duplicates and fingerprints
def test_fingerprint_is_stable_and_case_and_space_insensitive_on_the_description():
    a = fingerprint(date(2026, 3, 1), 2590, "expense", "GrabFood  KL")
    b = fingerprint(date(2026, 3, 1), 2590, "expense", " grabfood kl ")

    assert a == b


@pytest.mark.parametrize(
    "changed",
    [
        (date(2026, 3, 2), 2590, "expense", "GrabFood KL"),
        (date(2026, 3, 1), 2591, "expense", "GrabFood KL"),
        (date(2026, 3, 1), 2590, "income", "GrabFood KL"),
        (date(2026, 3, 1), 2590, "expense", "GrabFood PJ"),
    ],
)
def test_fingerprint_changes_when_any_field_changes(changed):
    base = fingerprint(date(2026, 3, 1), 2590, "expense", "GrabFood KL")

    assert fingerprint(*changed) != base


def test_reimporting_the_same_file_flags_every_row_as_a_duplicate():
    first = parse_csv(SIGNED)
    stored = [r.fingerprint for r in first.rows]

    second = flag_duplicates(parse_csv(SIGNED).rows, stored)

    assert all(r.duplicate for r in second)
    assert not any(r.duplicate for r in first.rows)


def test_two_identical_purchases_in_one_file_are_not_duplicates_of_each_other():
    text = "Date,Description,Amount\n01/03/2026,Kopi,-5.00\n01/03/2026,Kopi,-5.00\n"

    rows = flag_duplicates(parse_csv(text).rows, existing_fingerprints=[])

    assert [r.duplicate for r in rows] == [False, False]


def test_duplicates_respect_how_many_copies_are_already_stored():
    text = "Date,Description,Amount\n01/03/2026,Kopi,-5.00\n01/03/2026,Kopi,-5.00\n"
    rows = parse_csv(text).rows
    one_copy_stored = [rows[0].fingerprint]

    flagged = flag_duplicates(rows, one_copy_stored)

    assert [r.duplicate for r in flagged] == [True, False]
