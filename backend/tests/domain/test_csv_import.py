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
    assert salary.issues  # a guessed income is flagged for review too (it would inflate income)


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


# ---------------------------------------------------------------- review fixes (P1)
def test_debit_amount_and_credit_amount_headers_are_a_debit_credit_layout():
    text = (
        "Date,Description,Debit Amount,Credit Amount\n"
        "01/03/2026,Mamak,12.50,\n"
        "02/03/2026,Salary March,,1500.00\n"
    )

    preview = parse_csv(text)

    assert [(r.type, r.amount_sen) for r in preview.rows] == [("expense", 1250), ("income", 150000)]
    assert preview.skipped == ()


def test_an_unsigned_file_flags_every_row_it_guessed_to_be_income():
    text = "Date,Description,Amount\n01/03/2026,Salary March,2000.00\n02/03/2026,Mamak,5.00\n"

    salary, mamak = parse_csv(text).rows

    assert salary.type == "income"
    assert any("assumed income" in issue for issue in salary.issues)
    assert mamak.type == "expense"
    assert any("no sign" in issue for issue in mamak.issues)


def test_an_amount_above_the_api_limit_is_skipped_with_a_reason():
    from app.domain.money import MAX_AMOUNT_SEN

    over = f"{MAX_AMOUNT_SEN // 100 + 1}.00"
    text = f"Date,Description,Amount\n01/03/2026,Huge,-{over}\n02/03/2026,Fine,-1.00\n"

    preview = parse_csv(text)

    assert [r.description for r in preview.rows] == ["Fine"]
    assert "too large" in preview.skipped[0].reason


def test_a_field_beyond_the_csv_modules_limit_is_a_coded_error_not_a_crash():
    text = "Date,Description,Amount\n01/03/2026," + "x" * 200_000 + ",-1.00\n"

    with pytest.raises(CsvImportError) as err:
        parse_csv(text)

    assert err.value.code == "CSV_PARSE_FAILED"


def test_a_very_wide_header_is_refused_quickly():
    text = (
        ",".join(f"col{i}" for i in range(5000)) + "\n" + ",".join("1" for _ in range(5000)) + "\n"
    )

    with pytest.raises(CsvImportError) as err:
        parse_csv(text)

    assert err.value.code == "CSV_PARSE_FAILED"


def test_a_file_of_millions_of_blank_looking_rows_stops_at_the_row_limit():
    text = "Date,Description,Amount\n" + "01/03/2026,x,-1.00\n" * (MAX_ROWS + 10)

    with pytest.raises(CsvImportError) as err:
        parse_csv(text)

    assert err.value.code == "CSV_TOO_MANY_ROWS"


def test_a_pathologically_long_date_cell_is_just_an_unparseable_date():
    text = "Date,Description,Amount\n" + "1" * 5000 + ",x,-1.00\n02/03/2026,Fine,-1.00\n"

    preview = parse_csv(text)

    assert [r.description for r in preview.rows] == ["Fine"]
    assert "date" in preview.skipped[0].reason


# ---------------------------------------------------------------- the file's own type and category
# The shape of a student's own budget sheet: type, date, item, amount, category. Rows are invented.
OWN_TABLE = (
    "Type,Date,Item,Amount (RM),Category\n"
    "expense,1/8/2025, Kopi Corner,6.8,Drink / Dessert\n"
    "expense,2/8/2025, Rice Stall,15.9, Food\n"
    "income,3/8/2025,Monthly Allowance,1000,Allowance\n"
    "expense,4/8/2025,Cinema,31,hangout\n"
)


def test_a_type_column_decides_the_direction_and_there_is_nothing_to_review():
    preview = parse_csv(OWN_TABLE)

    assert [r.type for r in preview.rows] == ["expense", "expense", "income", "expense"]
    assert all(r.issues == () for r in preview.rows)  # no "no sign on amount" note
    assert [r.amount_sen for r in preview.rows] == [680, 1590, 100000, 3100]


def test_a_category_column_is_taken_as_written_not_guessed():
    preview = parse_csv(OWN_TABLE)

    # "Kopi Corner" would be guessed as Other and "Rice Stall" as Other too; the file says better.
    assert [r.category_guess for r in preview.rows] == [
        "Drink / Dessert",  # the person's own category is kept verbatim
        "Food",  # leading space trimmed
        "Allowance",
        "hangout",
    ]


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("food", "Food"), ("  TRANSPORT ", "Transport"), ("other", "Other")],
)
def test_a_category_matching_the_apps_list_uses_the_apps_spelling(cell, expected):
    text = f"Type,Date,Item,Amount,Category\nexpense,01/03/2026,Thing,5.00,{cell}\n"

    assert parse_csv(text).rows[0].category_guess == expected


def test_an_empty_category_cell_falls_back_to_the_keyword_guess():
    text = "Type,Date,Item,Amount,Category\nexpense,01/03/2026,Mamak dinner,5.00,\n"

    assert parse_csv(text).rows[0].category_guess == "Food"


def test_the_reserved_bnpl_category_is_never_taken_from_a_file():
    text = "Type,Date,Item,Amount,Category\nexpense,01/03/2026,Mamak dinner,5.00,BNPL\n"

    (row,) = parse_csv(text).rows

    assert row.category_guess == "Food"  # plan payments are tagged by the app only (D-29)
    assert any("BNPL" in issue for issue in row.issues)


def test_a_very_long_category_is_cut_to_what_the_api_accepts():
    text = f"Type,Date,Item,Amount,Category\nexpense,01/03/2026,Thing,5.00,{'x' * 100}\n"

    assert len(parse_csv(text).rows[0].category_guess) == 60


@pytest.mark.parametrize(
    ("word", "kind"),
    [
        ("Expense", "expense"),
        (" income ", "income"),
        ("SAVINGS", "savings"),
        ("saving", "savings"),
        ("Spending", "expense"),
        ("debit", "expense"),
        ("DR", "expense"),
        ("Credit", "income"),
        ("deposit", "income"),
    ],
)
def test_type_words_are_matched_loosely(word, kind):
    text = f"Type,Date,Item,Amount\n{word},01/03/2026,Thing,5.00\n"

    (row,) = parse_csv(text).rows

    assert row.type == kind
    assert row.issues == ()


def test_an_unrecognised_type_word_falls_back_to_the_old_rules_and_says_so():
    # One recognised value keeps the column in use; the odd one is then flagged on its own row.
    text = "Type,Date,Item,Amount\nexpense,02/03/2026,A,1.00\ngift,01/03/2026,Salary March,5.00\n"

    row = parse_csv(text).rows[1]

    assert row.type == "income"  # the words in the item still say income
    assert any("gift" in issue and "not recognised" in issue for issue in row.issues)


def test_a_blank_type_cell_uses_the_file_level_rules():
    text = "Type,Date,Item,Amount\nexpense,01/03/2026,A,5.00\n,02/03/2026,B,6.00\n"

    first, second = parse_csv(text).rows

    assert first.issues == ()
    assert second.type == "expense" and "no sign" in second.issues[0]


def test_the_type_column_beats_the_sign_of_the_amount():
    text = (
        "Type,Date,Item,Amount\n"
        "income,01/03/2026,Refund from shop,-50.00\n"
        "expense,02/03/2026,B,-5.00\n"
    )

    refund, other = parse_csv(text).rows

    assert (refund.type, refund.amount_sen) == ("income", 5000)
    assert other.type == "expense"


def test_separate_income_and_expense_columns():
    text = (
        "Date,Item,Income,Expense\n"
        "01/08/2025,Allowance,1000,\n"
        "02/08/2025,Lunch,,12.5\n"
        "03/08/2025,Nothing,,\n"
    )

    preview = parse_csv(text)

    assert [(r.type, r.amount_sen) for r in preview.rows] == [("income", 100000), ("expense", 1250)]
    assert [s.row for s in preview.skipped] == [3]  # a row with neither is reported, not dropped


def test_an_expense_category_header_is_not_mistaken_for_an_expense_amount_column():
    text = "Date,Item,Amount,Expense Category\n01/08/2025,Lunch,-12.50,Food\n"

    (row,) = parse_csv(text).rows

    assert (row.amount_sen, row.category_guess) == (1250, "Food")


# ---------------------------------------------------------------- where the table starts
def test_title_lines_above_the_header_are_skipped():
    text = (
        "Statement for August 2025\n"
        "Account holder: someone\n"
        "\n"
        "Date,Item,Amount\n"
        "01/08/2025,Lunch,-5.00\n"
        "02/08/2025,Dinner,-6.00\n"
    )

    preview = parse_csv(text)

    assert [(r.row, r.description) for r in preview.rows] == [(1, "Lunch"), (2, "Dinner")]


def test_tab_separated_text_is_read():
    text = "Date\tItem\tAmount\n01/08/2025\tLunch\t-5.00\n"

    assert parse_csv(text).rows[0].amount_sen == 500


def test_a_comma_in_a_title_line_does_not_hide_a_semicolon_table():
    text = "Statement, August, 2025\nDate;Item;Amount\n01/08/2025;Lunch;-5.00\n"

    (row,) = parse_csv(text).rows

    assert (row.description, row.amount_sen) == ("Lunch", 500)


def test_a_header_further_down_than_the_scan_limit_is_not_found():
    from app.domain.csv_import import HEADER_SCAN_ROWS

    text = "note\n" * (HEADER_SCAN_ROWS + 1) + "Date,Item,Amount\n01/08/2025,Lunch,-5.00\n"

    with pytest.raises(CsvImportError) as err:
        parse_csv(text)

    assert err.value.code == "CSV_MISSING_COLUMNS"
