import pytest

from app.api.deps import get_today
from app.db import user_settings
from app.domain.csv_import import MAX_ROWS

CSV = """Date,Description,Amount
01/03/2026,GRABFOOD KUALA LUMPUR,-25.90
02/03/2026,Monthly allowance from Parents,"1,000.00"
03/03/2026,TNG toll reload,-10.00
"""


HEADER = "Date,Description,Amount\n"
ROW = "01/03/2026,x,-1.00\n"
NO_DATE_COLUMN = "Foo,Bar\n1,2\n"


@pytest.fixture(autouse=True)
def fixed_today(api):
    from datetime import date

    api.app.dependency_overrides[get_today] = lambda: date(2026, 6, 30)
    yield
    api.app.dependency_overrides.pop(get_today, None)


def upload(api, headers, content=CSV, name="bank.csv"):
    data = content.encode() if isinstance(content, str) else content
    return api.post("/api/import/csv", files={"file": (name, data, "text/csv")}, headers=headers)


def confirm_body(preview, only=None):
    rows = [
        {
            "date": r["date"],
            "amount_sen": r["amount_sen"],
            "type": r["type"],
            "category": r["category_guess"],
            "description": r["description"],
        }
        for r in preview["rows"]
        if only is None or only(r)
    ]
    return {"rows": rows}


# ------------------------------------------------------------------ preview
def test_preview_returns_parsed_rows_without_storing_anything(api, amir):
    res = upload(api, amir)

    assert res.status_code == 200
    preview = res.json()
    assert [(r["type"], r["amount_sen"], r["category_guess"]) for r in preview["rows"]] == [
        ("expense", 2590, "Food"),
        ("income", 100000, "Allowance"),
        ("expense", 1000, "Transport"),
    ]
    assert preview["rows"][0]["date"] == "2026-03-01"
    assert preview["rows"][0]["duplicate"] is False
    assert preview["skipped"] == [] and preview["duplicate_count"] == 0
    assert api.get("/api/summary/months", headers=amir).json()["months"] == []  # nothing written


def test_preview_reports_skipped_rows_with_reasons(api, amir):
    res = upload(api, amir, CSV + "not a date,Lunch,-5.00\n01/03/2026,Zero,0.00\n")

    skipped = res.json()["skipped"]
    assert [s["row"] for s in skipped] == [4, 5]
    assert "date" in skipped[0]["reason"]
    assert len(res.json()["rows"]) == 3


@pytest.mark.parametrize(
    ("content", "name", "code"),
    [
        pytest.param(CSV, "bank.pdf", "wrong_file_type", id="pdf-extension"),
        pytest.param(CSV, "bank", "wrong_file_type", id="no-extension"),
        pytest.param("", "bank.csv", "csv_no_rows", id="empty-file"),
        pytest.param(HEADER, "bank.csv", "csv_no_rows", id="header-only"),
        pytest.param(NO_DATE_COLUMN, "bank.csv", "csv_missing_columns", id="no-date-column"),
        pytest.param(b"a" * (5 * 1024 * 1024 + 1), "bank.csv", "file_too_large", id="over-5mb"),
        pytest.param(
            HEADER + ROW * (MAX_ROWS + 1), "bank.csv", "csv_too_many_rows", id="too-many-rows"
        ),
    ],
)
def test_unusable_uploads_are_rejected_with_a_code(api, amir, content, name, code):
    res = upload(api, amir, content, name)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == code


def test_a_file_that_is_not_valid_utf8_does_not_crash(api, amir):
    content = b"Date,Description,Amount\n01/03/2026,Caf\xe9 au lait,-5.00\n"

    res = upload(api, amir, content)

    assert res.status_code == 200
    assert res.json()["rows"][0]["amount_sen"] == 500


def test_a_missing_file_is_a_validation_error(api, amir):
    res = api.post("/api/import/csv", headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "validation_error"


# ------------------------------------------------------------------ confirm
def test_confirm_stores_the_rows_and_marks_history_imported(api, amir, fake_db):
    preview = upload(api, amir).json()

    res = api.post("/api/import/confirm", json=confirm_body(preview), headers=amir)

    assert res.status_code == 200
    assert res.json() == {"created": 3}
    months = api.get("/api/summary/months", headers=amir).json()["months"]
    assert months[0]["income_sen"] == 100000 and months[0]["spend_sen"] == 3590
    stored = api.get("/api/transactions?start=2026-03-01&end=2026-03-31", headers=amir).json()
    assert {t["source"] for t in stored} == {"csv"}
    user_id = api.get("/api/auth/me", headers=amir).json()["id"]
    assert user_settings.get(fake_db, user_id)["onboarding_state"] == "history_imported"


def test_confirm_stores_only_the_rows_the_user_kept(api, amir):
    preview = upload(api, amir).json()

    res = api.post(
        "/api/import/confirm",
        json=confirm_body(preview, only=lambda r: r["type"] == "income"),
        headers=amir,
    )

    assert res.json() == {"created": 1}


def test_uploading_the_same_file_again_flags_every_row_as_a_duplicate(api, amir):
    api.post("/api/import/confirm", json=confirm_body(upload(api, amir).json()), headers=amir)

    again = upload(api, amir).json()

    assert again["duplicate_count"] == 3
    assert all(r["duplicate"] for r in again["rows"])


def test_a_partial_overlap_flags_only_the_overlapping_rows(api, amir):
    first = upload(api, amir, CSV).json()
    api.post(
        "/api/import/confirm",
        json=confirm_body(first, only=lambda r: r["type"] == "income"),
        headers=amir,
    )

    again = upload(api, amir, CSV).json()

    assert [r["duplicate"] for r in again["rows"]] == [False, True, False]
    assert again["duplicate_count"] == 1


@pytest.mark.parametrize(
    "bad_row",
    [
        {"amount_sen": 0},
        {"amount_sen": 12.5},
        {"type": "gift"},
        {"category": ""},
        {"date": "01/03/2026"},
        {"unexpected": 1},
    ],
)
def test_confirm_revalidates_every_row(api, amir, bad_row):
    row = {
        "date": "2026-03-01",
        "amount_sen": 100,
        "type": "expense",
        "category": "Food",
        "description": None,
    } | bad_row

    res = api.post("/api/import/confirm", json={"rows": [row]}, headers=amir)

    assert res.status_code == 422
    assert api.get("/api/summary/months", headers=amir).json()["months"] == []


def test_confirm_needs_at_least_one_row_and_at_most_the_limit(api, amir):
    row = {"date": "2026-03-01", "amount_sen": 1, "type": "expense", "category": "Food"}

    assert api.post("/api/import/confirm", json={"rows": []}, headers=amir).status_code == 422
    assert (
        api.post(
            "/api/import/confirm", json={"rows": [row] * (MAX_ROWS + 1)}, headers=amir
        ).status_code
        == 422
    )


# ------------------------------------------------------------------ isolation and auth
def test_one_users_import_is_invisible_to_another(api, amir, siti):
    api.post("/api/import/confirm", json=confirm_body(upload(api, amir).json()), headers=amir)

    sitis_preview = upload(api, siti).json()

    assert sitis_preview["duplicate_count"] == 0  # her fingerprints are her own
    assert api.get("/api/summary/months", headers=siti).json()["months"] == []


def test_import_routes_require_login(api):
    assert (
        api.post("/api/import/csv", files={"file": ("a.csv", b"x", "text/csv")}).status_code == 401
    )
    assert api.post("/api/import/confirm", json={"rows": []}).status_code == 401


# ------------------------------------------------------------------ own columns and Excel
OWN_TABLE = (
    "Type,Date,Item,Amount (RM),Category\n"
    "expense,1/8/2025, Kopi Corner,6.8,Drink / Dessert\n"
    "expense,2/8/2025,Rice Stall,15.9, Food\n"
    "income,3/8/2025,Monthly Allowance,1000,Allowance\n"
)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def own_table_workbook(extra_sheets=None) -> bytes:
    import io
    from datetime import datetime

    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Aug"
    sheet.append(["Type", "Date", "Item", "Amount (RM)", "Category"])
    sheet.append(["expense", datetime(2025, 8, 1), " Kopi Corner", 6.8, "Drink / Dessert"])
    sheet.append(["expense", datetime(2025, 8, 2), "Rice Stall", 15.9, " Food"])
    sheet.append(["income", datetime(2025, 8, 3), "Monthly Allowance", 1000, "Allowance"])
    for name, rows in (extra_sheets or {}).items():
        extra = book.create_sheet(name)
        for row in rows:
            extra.append(row)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def upload_xlsx(api, headers, content, name="budget.xlsx"):
    return api.post("/api/import/csv", files={"file": (name, content, XLSX)}, headers=headers)


def test_the_files_own_type_and_category_columns_are_what_the_preview_shows(api, amir):
    rows = upload(api, amir, OWN_TABLE).json()["rows"]

    assert [(r["type"], r["category_guess"], r["issues"]) for r in rows] == [
        ("expense", "Drink / Dessert", []),
        ("expense", "Food", []),
        ("income", "Allowance", []),
    ]


def test_an_excel_file_gives_the_same_preview_as_the_same_table_as_csv(api, amir):
    from_csv = upload(api, amir, OWN_TABLE).json()

    res = upload_xlsx(api, amir, own_table_workbook())

    assert res.status_code == 200
    assert res.json()["rows"] == from_csv["rows"]
    assert res.json()["notes"] == []


def test_a_sheet_that_is_not_a_table_comes_back_as_a_note(api, amir):
    book = own_table_workbook({"Summary": [["Total"], [22.7]]})

    res = upload_xlsx(api, amir, book)

    assert len(res.json()["rows"]) == 3
    assert len(res.json()["notes"]) == 1 and "Summary" in res.json()["notes"][0]


def test_a_category_of_the_persons_own_is_stored_as_written_after_confirm(api, amir):
    preview = upload_xlsx(api, amir, own_table_workbook()).json()

    api.post("/api/import/confirm", json=confirm_body(preview), headers=amir)

    stored = api.get("/api/transactions?start=2025-08-01&end=2025-08-31", headers=amir).json()
    assert sorted(t["category"] for t in stored) == ["Allowance", "Drink / Dessert", "Food"]


def test_an_old_xls_file_is_refused_with_how_to_convert_it(api, amir):
    res = upload(api, amir, b"\xd0\xcf\x11\xe0", "budget.xls")

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "wrong_file_type"
    assert ".xlsx" in res.json()["detail"]["message"]


def test_a_broken_workbook_is_a_coded_error_not_a_server_error(api, amir):
    res = upload_xlsx(api, amir, b"PK\x03\x04 this is not really a workbook")

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "excel_unreadable"


def test_a_workbook_that_unpacks_to_something_huge_is_refused(api, amir):
    import io
    import zipfile

    from app.domain.upload import MAX_WORKBOOK_UNCOMPRESSED

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("xl/worksheets/sheet1.xml", b"\0" * (MAX_WORKBOOK_UNCOMPRESSED + 1))

    res = upload_xlsx(api, amir, out.getvalue())

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "excel_too_large"


def test_tab_separated_text_files_are_accepted(api, amir):
    res = upload(api, amir, "Date\tItem\tAmount\n01/08/2025\tLunch\t-5.00\n", "export.tsv")

    assert res.status_code == 200 and res.json()["rows"][0]["amount_sen"] == 500


def test_a_workbook_import_is_still_one_users_own(api, amir, siti):
    api.post(
        "/api/import/confirm",
        json=confirm_body(upload_xlsx(api, amir, own_table_workbook()).json()),
        headers=amir,
    )

    assert upload_xlsx(api, amir, own_table_workbook()).json()["duplicate_count"] == 3
    assert upload_xlsx(api, siti, own_table_workbook()).json()["duplicate_count"] == 0
