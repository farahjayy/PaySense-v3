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
