from datetime import date

import pytest

from app.api.deps import get_today
from app.db import plans as plans_repo
from app.domain.schedule import build_schedule

TODAY = date(2026, 6, 30)


@pytest.fixture(autouse=True)
def fixed_today(api):
    api.app.dependency_overrides[get_today] = lambda: TODAY
    yield
    api.app.dependency_overrides.pop(get_today, None)


def body(**overrides):
    return {
        "date": "2026-06-10",
        "amount_sen": 1250,
        "type": "expense",
        "category": "Food",
        "description": "Nasi lemak",
    } | overrides


def post(api, headers, **overrides):
    res = api.post("/api/transactions", json=body(**overrides), headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


# ------------------------------------------------------------------ create
def test_create_returns_the_transaction(api, amir):
    res = api.post("/api/transactions", json=body(), headers=amir)

    assert res.status_code == 201
    created = res.json()
    assert created["amount_sen"] == 1250
    assert created["date"] == "2026-06-10"
    assert created["type"] == "expense" and created["category"] == "Food"
    assert created["is_bnpl"] is False and created["source"] == "manual"
    assert created["bnpl_plan_id"] is None and created["recurring_item_id"] is None
    assert "user_id" not in created


@pytest.mark.parametrize(
    "bad",
    [
        {"amount_sen": 12.5},
        {"amount_sen": "1250"},
        {"amount_sen": 0},
        {"amount_sen": -1},
        {"amount_sen": True},
        {"type": "gift"},
        {"category": ""},
        {"date": "10/06/2026"},
        {"date": "not a date"},
    ],
)
def test_create_rejects_bad_input_with_the_envelope(api, amir, bad):
    res = api.post("/api/transactions", json=body(**bad), headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "validation_error"


def test_create_can_link_to_the_users_own_recurring_item(api, amir):
    item = api.post(
        "/api/recurring-items",
        json={
            "kind": "income",
            "name": "Allowance",
            "amount_sen": 80000,
            "cadence": "monthly",
            "anchor_date": "2026-01-01",
        },
        headers=amir,
    ).json()

    created = post(api, amir, type="income", category="Allowance", recurring_item_id=item["id"])

    assert created["recurring_item_id"] == item["id"]


def test_create_cannot_link_to_another_users_recurring_item(api, amir, siti):
    item = api.post(
        "/api/recurring-items",
        json={
            "kind": "bill",
            "name": "Rent",
            "amount_sen": 50000,
            "cadence": "monthly",
            "anchor_date": "2026-01-01",
        },
        headers=siti,
    ).json()

    res = api.post("/api/transactions", json=body(recurring_item_id=item["id"]), headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "recurring_item_not_found"


# ------------------------------------------------------------------ list
def test_list_defaults_to_the_last_90_days_newest_first(api, amir):
    post(api, amir, date="2026-06-01", amount_sen=100)
    post(api, amir, date="2026-06-20", amount_sen=200)
    post(api, amir, date="2026-01-01", amount_sen=300)  # older than 90 days before 30 Jun

    res = api.get("/api/transactions", headers=amir)

    assert [t["amount_sen"] for t in res.json()["transactions"]] == [200, 100]


def test_list_filters_by_range_type_and_category(api, amir):
    post(api, amir, date="2026-03-01", amount_sen=100)
    post(api, amir, date="2026-03-15", amount_sen=200, type="income", category="Salary")
    post(api, amir, date="2026-04-01", amount_sen=300)

    in_march = api.get("/api/transactions?start=2026-03-01&end=2026-03-31", headers=amir).json()[
        "transactions"
    ]
    incomes = api.get(
        "/api/transactions?start=2026-03-01&end=2026-04-30&type=income", headers=amir
    ).json()["transactions"]
    salary = api.get(
        "/api/transactions?start=2026-03-01&end=2026-04-30&category=Salary", headers=amir
    ).json()["transactions"]

    assert [t["amount_sen"] for t in in_march] == [200, 100]
    assert [t["amount_sen"] for t in incomes] == [200]
    assert [t["amount_sen"] for t in salary] == [200]


def test_list_rejects_an_inverted_range(api, amir):
    res = api.get("/api/transactions?start=2026-05-01&end=2026-04-01", headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "invalid_range"


def test_list_rejects_an_unknown_type_filter(api, amir):
    assert api.get("/api/transactions?type=gift", headers=amir).status_code == 422


def test_list_shows_only_the_callers_transactions(api, amir, siti):
    post(api, amir, amount_sen=111)
    post(api, siti, amount_sen=222)

    assert [
        t["amount_sen"] for t in api.get("/api/transactions", headers=amir).json()["transactions"]
    ] == [111]
    assert [
        t["amount_sen"] for t in api.get("/api/transactions", headers=siti).json()["transactions"]
    ] == [222]


# ------------------------------------------------------------------ update / delete
def test_patch_changes_only_what_was_sent(api, amir):
    created = post(api, amir)

    res = api.patch(
        f"/api/transactions/{created['id']}",
        json={"amount_sen": 2000, "category": "Transport"},
        headers=amir,
    )

    assert res.status_code == 200
    assert (res.json()["amount_sen"], res.json()["category"]) == (2000, "Transport")
    assert res.json()["description"] == "Nasi lemak"


def test_patch_can_clear_the_description(api, amir):
    created = post(api, amir)

    res = api.patch(f"/api/transactions/{created['id']}", json={"description": None}, headers=amir)

    assert res.json()["description"] is None


@pytest.mark.parametrize(
    "patch",
    [
        {"user_id": "x"},
        {"source": "csv"},
        {"bnpl_plan_id": "x"},
        {"amount_sen": 0},
        {"type": "gift"},
    ],
)
def test_patch_rejects_fields_it_does_not_own_and_bad_values(api, amir, patch):
    created = post(api, amir)

    res = api.patch(f"/api/transactions/{created['id']}", json=patch, headers=amir)

    assert res.status_code == 422


def test_delete_removes_it(api, amir):
    created = post(api, amir)

    assert api.delete(f"/api/transactions/{created['id']}", headers=amir).status_code == 204
    assert api.get("/api/transactions", headers=amir).json()["transactions"] == []
    assert api.delete(f"/api/transactions/{created['id']}", headers=amir).status_code == 404


def test_another_users_transaction_is_a_404_for_patch_and_delete(api, amir, siti):
    created = post(api, amir)

    patched = api.patch(f"/api/transactions/{created['id']}", json={"amount_sen": 1}, headers=siti)
    deleted = api.delete(f"/api/transactions/{created['id']}", headers=siti)

    assert patched.status_code == deleted.status_code == 404
    assert patched.json()["detail"]["code"] == "transaction_not_found"
    assert (
        api.get("/api/transactions", headers=amir).json()["transactions"][0]["amount_sen"] == 1250
    )


def test_a_malformed_id_is_a_404_not_a_server_error(api, amir):
    assert (
        api.patch("/api/transactions/nope", json={"amount_sen": 1}, headers=amir).status_code == 404
    )
    assert api.delete("/api/transactions/nope", headers=amir).status_code == 404


def test_payments_logged_by_a_plan_belong_to_the_plan(api, amir, fake_db):
    user = api.get("/api/auth/me", headers=amir).json()
    instalments = build_schedule("atome", 30000, 0, 3, date(2026, 6, 5))
    plan = plans_repo.create_plan(
        fake_db,
        user["id"],
        {
            "item_name": "Phone",
            "provider": "atome",
            "provider_label": "Atome",
            "schedule_source": "provider_rule",
            "total_price_sen": 30000,
            "financed_sen": 30000,
            "upfront_sen": 0,
            "monthly_fee_rate_pct": 0,
            "num_installments": 3,
            "purchase_date": date(2026, 6, 5),
            "first_payment_date": instalments[0].due_date,
        },
        instalments,
    )
    (logged,) = api.get("/api/transactions", headers=amir).json()["transactions"]
    assert logged["bnpl_plan_id"] == plan["id"]

    patched = api.patch(f"/api/transactions/{logged['id']}", json={"amount_sen": 1}, headers=amir)
    deleted = api.delete(f"/api/transactions/{logged['id']}", headers=amir)

    assert patched.status_code == deleted.status_code == 409
    assert patched.json()["detail"]["code"] == "managed_by_plan"


# ------------------------------------------------------------------ month summary
def test_summary_is_empty_for_a_new_user(api, amir):
    res = api.get("/api/summary/months", headers=amir)

    assert res.status_code == 200
    assert res.json() == {"months": [], "history": None}


def test_summary_groups_by_month_and_nets_refunds_and_ignores_transfers(api, amir):
    post(api, amir, date="2026-04-02", type="income", category="Allowance", amount_sen=100000)
    post(api, amir, date="2026-04-10", amount_sen=30000)
    post(api, amir, date="2026-04-12", type="income", category="Refund", amount_sen=5000)
    post(api, amir, date="2026-04-15", category="Transfer", amount_sen=99999)
    post(api, amir, date="2026-05-03", amount_sen=2000)

    res = api.get("/api/summary/months", headers=amir).json()

    april, may = res["months"]
    assert april == {
        "month": "2026-04",
        "income_sen": 100000,
        "spend_sen": 25000,
        "refund_sen": 5000,
        "savings_sen": 0,
        "net_sen": 75000,
    }
    assert may["spend_sen"] == 2000 and may["net_sen"] == -2000
    assert res["history"] == {
        "first_date": "2026-04-02",
        "last_date": "2026-05-03",
        "distinct_months": 2,
        "span_days": 32,
        "days_since_last": 58,
    }


def test_summary_is_private_to_each_user(api, amir, siti):
    post(api, amir, amount_sen=5555)

    assert api.get("/api/summary/months", headers=siti).json() == {"months": [], "history": None}


# ------------------------------------------------------------------ auth
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/transactions"),
        ("post", "/api/transactions"),
        ("patch", "/api/transactions/x"),
        ("delete", "/api/transactions/x"),
        ("get", "/api/summary/months"),
    ],
)
def test_every_route_requires_login(api, method, path):
    assert getattr(api, method)(path).status_code == 401
