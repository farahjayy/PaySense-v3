"""Edge cases found by review of the spreadsheet import: split layouts with a missing last cell,
title rows that look like headers, a wrong delimiter that finds a false header, one junk sheet among
good ones, and a Type column that holds something other than income or expense."""

import io
from datetime import datetime

import pytest
from openpyxl import Workbook

from app.domain import upload
from app.domain.csv_import import MAX_COLUMNS, MAX_ROWS, CsvImportError, parse_csv
from app.domain.upload import parse_upload

D = datetime(2025, 8, 1)


def workbook(sheets: dict[str, list[list]]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    for name, rows in sheets.items():
        sheet = book.create_sheet(name)
        for row in rows:
            sheet.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# ---------------------------------------------------------------- rows that stop early
def test_an_income_only_row_in_an_income_expense_sheet_is_read():
    # Excel leaves the trailing empty cell out, so the row is shorter than the header.
    rows = [
        ["Date", "Item", "Income", "Expense"],
        [D, "Allowance", 1000, None],
        [D, "Lunch", None, 5],
    ]

    preview = parse_upload("excel", workbook({"S": rows}))

    assert [(r.type, r.amount_sen) for r in preview.rows] == [("income", 100000), ("expense", 500)]
    assert preview.skipped == ()


def test_a_credit_only_row_in_a_debit_credit_sheet_is_read():
    rows = [
        ["Date", "Details", "Debit", "Credit"],
        [D, "Gaji", None, 1500],
        [D, "Mamak", 12.5, None],
    ]

    preview = parse_upload("excel", workbook({"S": rows}))

    assert [(r.type, r.amount_sen) for r in preview.rows] == [("income", 150000), ("expense", 1250)]


def test_a_short_row_in_a_csv_split_layout_is_read_too():
    text = "Date,Item,Income,Expense\n01/08/2025,Allowance,1000\n"

    assert parse_csv(text).rows[0].type == "income"


@pytest.mark.parametrize("dash", ["-", "–", "—"])
def test_a_dash_in_the_empty_column_of_a_split_layout_means_empty(dash):
    text = (
        f"Date,Item,Income,Expense\n01/08/2025,Allowance,1000,{dash}\n02/08/2025,Lunch,{dash},5\n"
    )

    preview = parse_csv(text)

    assert [(r.type, r.amount_sen) for r in preview.rows] == [("income", 100000), ("expense", 500)]
    assert preview.skipped == ()


# ---------------------------------------------------------------- a title that looks like a header
@pytest.mark.parametrize(
    "title",
    [
        "Date range: 1 Aug - 31 Aug,Total amount: 500",
        "Last updated,Amount due",
    ],
)
def test_a_title_row_that_mentions_date_and_amount_is_not_taken_for_the_header(title):
    text = f"{title}\nDate,Item,Amount\n01/08/2025,Lunch,-5.00\n"

    (row,) = parse_csv(text).rows

    assert (row.description, row.amount_sen) == ("Lunch", 500)


def test_a_workbook_title_row_that_looks_like_a_header_is_skipped_too():
    rows = [["Last updated", "Amount due"], ["Date", "Item", "Amount"], [D, "Lunch", -5]]

    (row,) = parse_upload("excel", workbook({"S": rows})).rows

    assert (row.description, row.amount_sen) == ("Lunch", 500)


def test_a_header_with_only_unreadable_rows_is_still_reported_not_hidden():
    # With no better candidate, the first header-like row is kept so the bad rows are listed.
    with pytest.raises(CsvImportError) as err:
        parse_csv("Date,Description,Amount\nnope,Lunch,-5.00\n")

    assert err.value.code == "CSV_NO_ROWS"


# ---------------------------------------------------------------- a wrong delimiter
def test_a_title_with_more_commas_than_the_table_has_semicolons_still_imports():
    text = "Statement, for, August, 2025, issued, today\nDate;Item;Amount\n01/08/2025;Lunch;-5.00\n"

    (row,) = parse_csv(text).rows

    assert (row.description, row.amount_sen) == ("Lunch", 500)


def test_a_false_header_under_the_likeliest_delimiter_falls_through_to_the_next():
    text = "Statement date, amount in RM, a, b, c, d\nDate;Item;Amount\n01/08/2025;Lunch;-5.00\n"

    (row,) = parse_csv(text).rows

    assert (row.description, row.amount_sen) == ("Lunch", 500)


# ---------------------------------------------------------------- one junk sheet among good ones
def test_a_sheet_over_the_row_limit_is_noted_and_the_good_sheet_is_still_read():
    good = [["Date", "Item", "Amount"], [D, "Lunch", -5]]
    junk = [["v1"]] * (MAX_ROWS + 100)

    preview = parse_upload("excel", workbook({"Aug": good, "Lookup": junk}))

    assert [r.description for r in preview.rows] == ["Lunch"]
    assert len(preview.notes) == 1 and "Lookup" in preview.notes[0]


def test_a_sheet_that_is_too_wide_refuses_the_workbook_before_it_is_loaded():
    good = [["Date", "Item", "Amount"], [D, "Lunch", -5]]
    wide = [[f"c{i}" for i in range(MAX_COLUMNS + 6)]]

    with pytest.raises(CsvImportError) as err:
        parse_upload("excel", workbook({"Aug": good, "Cal": wide}))

    assert err.value.code == "CSV_PARSE_FAILED"


def test_when_every_sheet_breaks_a_limit_the_limit_is_the_error():
    junk = [["v1"]] * (MAX_ROWS + 100)

    with pytest.raises(CsvImportError) as err:
        parse_upload("excel", workbook({"A": junk}))

    assert err.value.code == "CSV_TOO_MANY_ROWS"


# --- a Type column that is not a direction
def test_a_type_column_that_holds_categories_is_not_used_and_says_so_once():
    text = (
        "Type,Date,Item,Amount\n"
        "Food,01/08/2025,Lunch,-5.00\n"
        "Transport,02/08/2025,Grab,-6.00\n"
        "Food,03/08/2025,Allowance,20.00\n"
    )

    preview = parse_csv(text)

    assert [r.type for r in preview.rows] == ["expense", "expense", "income"]  # from the sign
    assert all(r.issues == () for r in preview.rows)
    assert len(preview.notes) == 1 and "Type" in preview.notes[0]


def test_a_type_column_with_one_odd_value_still_flags_just_that_row():
    text = "Type,Date,Item,Amount\nexpense,01/08/2025,A,5\ngift,02/08/2025,B,6\n"

    first, second = parse_csv(text).rows

    assert first.issues == () and "not recognised" in second.issues[0]


# --- sharper checks of earlier behaviour
def test_a_formula_with_no_stored_result_reads_as_a_missing_amount():
    rows = [["Date", "Item", "Amount"], [D, "a", "=5+1"], [D, "b", 3]]

    preview = parse_upload("excel", workbook({"S": rows}))

    assert [(s.row, s.reason) for s in preview.skipped] == [(1, "missing amount")]


def test_a_third_decimal_reads_as_an_invalid_amount():
    rows = [["Date", "Item", "Amount"], [D, "a", 1.234], [D, "b", 2]]

    preview = parse_upload("excel", workbook({"S": rows}))

    assert [(s.row, s.reason) for s in preview.skipped] == [(1, "invalid amount '1.234'")]


def test_a_fourth_decimal_is_refused_not_rounded_away():
    rows = [["Date", "Item", "Amount"], [D, "a", 1.2300004], [D, "b", 2]]

    preview = parse_upload("excel", workbook({"S": rows}))

    assert [r.description for r in preview.rows] == ["b"]


def test_rows_past_the_scan_cap_are_not_read(monkeypatch):
    monkeypatch.setattr(upload, "MAX_SCAN_ROWS", 5)
    rows = [["Date", "Item", "Amount"], [D, "a", 1], [D, "b", 2], [D, "c", 3], [D, "d", 4]]
    book = Workbook()
    sheet = book.active
    for row in rows:
        sheet.append(row)
    sheet.cell(row=8, column=1, value=D)
    sheet.cell(row=8, column=2, value="past the cap")
    sheet.cell(row=8, column=3, value=9)
    out = io.BytesIO()
    book.save(out)

    preview = parse_upload("excel", out.getvalue())

    assert [r.description for r in preview.rows] == ["a", "b", "c", "d"]


def test_a_text_file_with_one_stray_invalid_byte_still_imports_its_rows():
    data = b"Date,Item,Amount\n01/08/2025,Lunch \xff,-5.00\n"

    (row,) = parse_upload("text", data).rows

    assert row.amount_sen == 500


# ---------------------------------------------------------------- reserved categories from a file
def test_a_transfer_category_is_kept_but_flagged_because_it_leaves_the_forecast():
    text = "Type,Date,Item,Amount,Category\nexpense,01/08/2025,Sent to a friend,50,Transfer\n"

    (row,) = parse_csv(text).rows

    assert row.category_guess == "Transfer"
    assert any("left out" in issue for issue in row.issues)


def test_a_refund_category_on_an_expense_is_not_taken():
    text = "Type,Date,Item,Amount,Category\nexpense,01/08/2025,Mamak dinner,500,Refund\n"

    (row,) = parse_csv(text).rows

    assert row.category_guess == "Food"  # a refund nets against spending: only for money coming in
    assert any("Refund" in issue for issue in row.issues)


def test_a_refund_category_on_income_is_kept_without_a_warning():
    text = "Type,Date,Item,Amount,Category\nincome,01/08/2025,Shop returned money,50,refund\n"

    (row,) = parse_csv(text).rows

    assert (row.category_guess, row.issues) == ("Refund", ())


# ---------------------------------------------------------------- structure of a hostile workbook
def with_sheet_xml(good: bytes, sheet_xml: bytes) -> bytes:
    import zipfile

    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(good)) as source, zipfile.ZipFile(out, "w") as target:
        for item in source.infolist():
            data = sheet_xml if item.filename == "xl/worksheets/sheet1.xml" else source.read(item)
            target.writestr(item.filename, data)
    return out.getvalue()


MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def sheet_of_cells(per_row: int, rows: int = 1) -> bytes:
    cells = b"<c/>" * per_row
    body = b"".join(b'<row r="%d">%s</row>' % (n + 1, cells) for n in range(rows))
    return b'<worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>' % (MAIN.encode(), body)


def good_workbook() -> bytes:
    return workbook({"S": [["Date", "Item", "Amount"], [D, "Lunch", -5]]})


def test_a_row_with_more_cells_than_the_column_limit_is_refused_before_it_is_loaded():
    hostile = with_sheet_xml(good_workbook(), sheet_of_cells(MAX_COLUMNS + 2))

    with pytest.raises(CsvImportError) as err:
        upload.read_workbook(hostile)

    assert err.value.code == "CSV_PARSE_FAILED"


def test_a_sheet_with_too_many_cells_overall_is_refused(monkeypatch):
    monkeypatch.setattr(upload, "MAX_CELLS_PER_SHEET", 50)
    hostile = with_sheet_xml(good_workbook(), sheet_of_cells(10, rows=6))

    with pytest.raises(CsvImportError) as err:
        upload.read_workbook(hostile)

    assert err.value.code == "EXCEL_TOO_LARGE"


def test_a_worksheet_part_over_its_own_size_cap_is_refused(monkeypatch):
    monkeypatch.setattr(upload, "MAX_WORKSHEET_BYTES", 200)

    with pytest.raises(CsvImportError) as err:
        upload.read_workbook(good_workbook())

    assert err.value.code == "EXCEL_TOO_LARGE"


def test_a_shared_strings_table_over_its_cap_is_refused(monkeypatch):
    import zipfile

    monkeypatch.setattr(upload, "MAX_SHARED_STRINGS_BYTES", 100)
    out = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(good_workbook())) as source,
        zipfile.ZipFile(out, "w") as target,
    ):
        for item in source.infolist():
            target.writestr(item.filename, source.read(item))
        table = b'<sst xmlns="%s">%s</sst>' % (MAIN.encode(), b"<si><t>a</t></si>" * 50)
        target.writestr("xl/sharedStrings.xml", table)

    with pytest.raises(CsvImportError) as err:
        upload.read_workbook(out.getvalue())

    assert err.value.code == "EXCEL_TOO_LARGE"


def test_a_workbook_cannot_make_the_server_scan_rows_without_end_across_sheets(monkeypatch):
    monkeypatch.setattr(upload, "MAX_TOTAL_SCAN_ROWS", 6)
    rows = [["Date", "Item", "Amount"], [D, "a", 1], [D, "b", 2]]

    with pytest.raises(CsvImportError) as err:
        upload.read_workbook(workbook({"A": rows, "B": rows, "C": rows}))

    assert err.value.code == "CSV_TOO_MANY_ROWS"


def test_a_malformed_sheet_part_is_a_coded_error():
    hostile = with_sheet_xml(good_workbook(), b"<worksheet><sheetData><row>")

    with pytest.raises(CsvImportError) as err:
        upload.read_workbook(hostile)

    assert err.value.code == "EXCEL_UNREADABLE"


def test_when_the_server_is_busy_reading_other_workbooks_the_person_is_told_to_retry(monkeypatch):
    import threading

    gate = threading.BoundedSemaphore(1)
    gate.acquire()
    monkeypatch.setattr(upload, "_GATE", gate)
    monkeypatch.setattr(upload, "GATE_WAIT_SECONDS", 0.05)

    with pytest.raises(CsvImportError) as err:
        parse_upload("excel", good_workbook())

    assert err.value.code == "IMPORT_BUSY"


def test_the_gate_is_released_after_a_workbook_is_read_or_refused():
    parse_upload("excel", good_workbook())
    with pytest.raises(CsvImportError):
        parse_upload("excel", b"not a workbook")

    assert parse_upload("excel", good_workbook()).rows  # still gets in
