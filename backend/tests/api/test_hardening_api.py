"""Ordinary-but-awkward input must produce a clear 4xx, never a 500 (P1 review, HIGH)."""

from datetime import UTC, date, datetime

import pytest
from postgrest import APIError

from app.api.deps import get_today, malaysia_today
from app.db import recurring_items, transactions, user_settings


@pytest.fixture(autouse=True)
def fixed_today(api):
    api.app.dependency_overrides[get_today] = lambda: date(2026, 6, 30)
    yield
    api.app.dependency_overrides.pop(get_today, None)


def txn(**overrides):
    return {
        "date": "2026-06-10",
        "amount_sen": 1250,
        "type": "expense",
        "category": "Food",
    } | overrides


def item(**overrides):
    return {
        "kind": "bill",
        "name": "Rent",
        "amount_sen": 50000,
        "cadence": "monthly",
        "anchor_date": "2026-01-01",
    } | overrides


def is_clean_422(res):
    return res.status_code == 422 and res.json()["detail"]["code"] == "validation_error"


# ------------------------------------------------------------------ blank and NUL text
@pytest.mark.parametrize("field", ["category", "description", "account_name"])
def test_text_fields_reject_a_nul_character(api, amir, field):
    res = api.post("/api/transactions", json=txn(**{field: "bad\u0000text"}), headers=amir)

    assert is_clean_422(res)


def test_a_blank_category_is_rejected_after_trimming(api, amir):
    assert is_clean_422(api.post("/api/transactions", json=txn(category="   "), headers=amir))


def test_a_blank_description_is_simply_stored_as_nothing(api, amir):
    res = api.post("/api/transactions", json=txn(description="   "), headers=amir)

    assert res.status_code == 201 and res.json()["description"] is None


def test_text_is_trimmed(api, amir):
    res = api.post("/api/transactions", json=txn(category="  Food  "), headers=amir)

    assert res.json()["category"] == "Food"


def test_a_blank_recurring_item_name_is_rejected(api, amir):
    assert is_clean_422(api.post("/api/recurring-items", json=item(name="  "), headers=amir))


def test_a_blank_import_category_is_rejected(api, amir):
    row = {"date": "2026-03-01", "amount_sen": 100, "type": "expense", "category": "  "}

    assert is_clean_422(api.post("/api/import/confirm", json={"rows": [row]}, headers=amir))


def test_a_nul_in_an_imported_description_is_rejected_not_a_database_error(api, amir):
    row = {"date": "2026-03-01", "amount_sen": 100, "type": "expense", "category": "Food"}
    row["description"] = "a\u0000b"

    assert is_clean_422(api.post("/api/import/confirm", json={"rows": [row]}, headers=amir))


# ------------------------------------------------------------------ explicit nulls on PATCH
@pytest.mark.parametrize("field", ["amount_sen", "date", "type", "category"])
def test_patching_a_required_transaction_field_to_null_is_rejected(api, amir, field):
    created = api.post("/api/transactions", json=txn(), headers=amir).json()

    res = api.patch(f"/api/transactions/{created['id']}", json={field: None}, headers=amir)

    assert is_clean_422(res)
    assert api.get("/api/transactions", headers=amir).json()[0]["amount_sen"] == 1250


@pytest.mark.parametrize("field", ["name", "amount_sen", "cadence", "anchor_date", "active"])
def test_patching_a_required_recurring_field_to_null_is_rejected(api, amir, field):
    created = api.post("/api/recurring-items", json=item(), headers=amir).json()

    res = api.patch(f"/api/recurring-items/{created['id']}", json={field: None}, headers=amir)

    assert is_clean_422(res)
    assert api.get("/api/recurring-items", headers=amir).json()[0]["active"] is True


def test_nullable_fields_can_still_be_cleared(api, amir):
    created = api.post("/api/transactions", json=txn(description="x"), headers=amir).json()

    res = api.patch(f"/api/transactions/{created['id']}", json={"description": None}, headers=amir)

    assert res.status_code == 200 and res.json()["description"] is None


def test_an_empty_patch_changes_nothing_and_succeeds(api, amir):
    created = api.post("/api/recurring-items", json=item(), headers=amir).json()

    res = api.patch(f"/api/recurring-items/{created['id']}", json={}, headers=amir)

    assert res.status_code == 200 and res.json()["name"] == "Rent"


# ------------------------------------------------------------------ absurd dates
@pytest.mark.parametrize("day", ["0001-01-01", "1999-12-31", "9999-12-31", "2101-01-01"])
def test_dates_outside_a_sane_range_are_rejected_everywhere(api, amir, day):
    assert is_clean_422(api.post("/api/transactions", json=txn(date=day), headers=amir))
    assert is_clean_422(api.post("/api/recurring-items", json=item(anchor_date=day), headers=amir))
    plan = {
        "provider": "spaylater",
        "item_name": "Phone",
        "purchase_date": day,
        "num_installments": 3,
        "total_price_sen": 30000,
    }
    assert is_clean_422(api.post("/api/plans/preview", json=plan, headers=amir))


@pytest.mark.parametrize("params", ["end=0001-01-01", "start=9999-12-31", "start=1900-01-01"])
def test_list_filters_reject_absurd_dates_instead_of_overflowing(api, amir, params):
    res = api.get(f"/api/transactions?{params}", headers=amir)

    assert res.status_code == 422


# ------------------------------------------------------------------ a pathological CSV
def test_a_csv_with_an_enormous_single_field_is_a_clean_error(api, amir):
    content = "Date,Description,Amount\n01/03/2026," + "x" * 200_000 + ",-1.00\n"

    res = api.post(
        "/api/import/csv", files={"file": ("big.csv", content.encode(), "text/csv")}, headers=amir
    )

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "csv_parse_failed"


def test_an_imported_amount_too_large_for_the_api_is_skipped_in_the_preview(api, amir):
    content = "Date,Description,Amount\n01/03/2026,Huge,-9999999999999.00\n02/03/2026,Fine,-1.00\n"

    res = api.post(
        "/api/import/csv", files={"file": ("a.csv", content.encode(), "text/csv")}, headers=amir
    )

    body = res.json()
    assert [r["description"] for r in body["rows"]] == ["Fine"]
    assert "too large" in body["skipped"][0]["reason"]


# ------------------------------------------------------------------ database errors
def _boom(code):
    def raiser(*args, **kwargs):
        raise APIError({"message": "db said no", "code": code, "details": "secret detail"})

    return raiser


@pytest.mark.parametrize(
    ("code", "status", "envelope"),
    [
        ("23505", 409, "conflict"),
        ("23503", 409, "conflict"),
        ("22P05", 422, "invalid_value"),
        ("23514", 422, "invalid_value"),
        ("XX000", 500, "internal_error"),
    ],
)
def test_a_database_rejection_becomes_a_clean_response(
    api, amir, monkeypatch, code, status, envelope
):
    monkeypatch.setattr(transactions, "create", _boom(code))

    res = api.post("/api/transactions", json=txn(), headers=amir)

    assert res.status_code == status
    assert res.json()["detail"]["code"] == envelope
    assert "secret detail" not in res.text and "db said no" not in res.text


# ------------------------------------------------------------------ time zone
def test_today_is_the_date_in_malaysia_not_utc():
    late_utc = datetime(2026, 10, 8, 17, 0, tzinfo=UTC)  # 01:00 on 9 Oct in Kuala Lumpur
    early_utc = datetime(2026, 10, 8, 15, 59, tzinfo=UTC)  # 23:59 on 8 Oct in Kuala Lumpur

    assert malaysia_today(late_utc) == date(2026, 10, 9)
    assert malaysia_today(early_utc) == date(2026, 10, 8)


# ------------------------------------------------------------------ onboarding
def test_a_later_import_does_not_send_onboarding_backwards(api, amir, fake_db):
    user_id = api.get("/api/auth/me", headers=amir).json()["id"]
    user_settings.set_onboarding_state(fake_db, user_id, "complete")
    row = {"date": "2026-03-01", "amount_sen": 100, "type": "expense", "category": "Food"}

    res = api.post("/api/import/confirm", json={"rows": [row]}, headers=amir)

    assert res.status_code == 200
    assert user_settings.get(fake_db, user_id)["onboarding_state"] == "complete"


def test_an_import_still_succeeds_if_the_onboarding_note_cannot_be_written(api, amir, monkeypatch):
    monkeypatch.setattr(user_settings, "advance_onboarding_state", _boom("XX000"))
    row = {"date": "2026-03-01", "amount_sen": 100, "type": "expense", "category": "Food"}

    res = api.post("/api/import/confirm", json={"rows": [row]}, headers=amir)

    assert res.status_code == 200 and res.json() == {"created": 1}


def test_advance_only_moves_forward(db=None):
    from app.db.users import create
    from tests.fakes import FakeSupabase

    fake = FakeSupabase()
    uid = create(fake, username="amir", display_name="Amir")["id"]

    assert (
        user_settings.advance_onboarding_state(fake, uid, "history_imported")["onboarding_state"]
        == "history_imported"
    )
    assert (
        user_settings.advance_onboarding_state(fake, uid, "new")["onboarding_state"]
        == "history_imported"
    )
    assert (
        user_settings.advance_onboarding_state(fake, uid, "complete")["onboarding_state"]
        == "complete"
    )


# ---------------------------------------------- the contract documents its errors
def test_conflict_responses_are_documented_with_the_error_envelope(api):
    spec = api.get("/openapi.json").json()
    conflicts = [
        spec["paths"]["/api/plans/{plan_id}/installments/{seq}/pay"]["post"]["responses"]["409"],
        spec["paths"]["/api/plans/{plan_id}/pay"]["post"]["responses"]["409"],
        spec["paths"]["/api/transactions/{transaction_id}"]["patch"]["responses"]["409"],
        spec["paths"]["/api/transactions/{transaction_id}"]["delete"]["responses"]["409"],
    ]

    for response in conflicts:
        ref = response["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ErrorEnvelope")


def test_limit_requests_reject_unknown_fields(api, amir):
    res = api.put(
        "/api/provider-limits/atome", json={"limit_sen": 100, "surprise": 1}, headers=amir
    )

    assert is_clean_422(res)


def test_recurring_repository_ignores_an_empty_patch(fake_db):
    from app.db.users import create

    uid = create(fake_db, username="zed", display_name="Zed")["id"]
    created = recurring_items.create(
        fake_db,
        uid,
        kind="bill",
        name="Rent",
        amount_sen=1,
        cadence="monthly",
        anchor_date=date(2026, 1, 1),
    )

    assert recurring_items.update(fake_db, uid, created["id"], {})["name"] == "Rent"
