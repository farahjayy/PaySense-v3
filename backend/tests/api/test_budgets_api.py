"""Budgets API (WP2): every route is user-scoped and needs a session."""

import pytest

from app.api.deps import get_today
from tests.api.conftest import _headers  # noqa: F401  (fixtures come from conftest)

MONTH = "2026-03"


@pytest.fixture(autouse=True)
def pinned_today(api):
    from datetime import date

    api.app.dependency_overrides[get_today] = lambda: date(2026, 3, 15)


def spend(api, headers, day, amount, category="Food"):
    body = {"date": day, "amount_sen": amount, "type": "expense", "category": category}
    assert api.post("/api/transactions", json=body, headers=headers).status_code == 201


def test_set_list_replace_and_delete_a_budget(api, amir):
    res = api.put("/api/budgets", json={"category": "food", "limit_sen": 40000}, headers=amir)
    assert res.status_code == 200
    assert res.json()["category"] == "Food"
    again = api.put("/api/budgets", json={"category": "FOOD", "limit_sen": 30000}, headers=amir)
    assert again.json()["limit_sen"] == 30000
    listed = api.get("/api/budgets", headers=amir).json()["budgets"]
    assert [(b["category"], b["limit_sen"]) for b in listed] == [("Food", 30000)]
    assert api.delete("/api/budgets", params={"category": "Food"}, headers=amir).status_code == 204
    assert api.get("/api/budgets", headers=amir).json()["budgets"] == []
    gone = api.delete("/api/budgets", params={"category": "Food"}, headers=amir)
    assert gone.status_code == 404
    assert gone.json()["detail"]["code"] == "budget_not_found"


def test_a_name_with_a_slash_travels_in_the_body_and_query(api, amir):
    body = {"category": "Drink/Dessert", "limit_sen": 5000}
    assert api.put("/api/budgets", json=body, headers=amir).status_code == 200
    res = api.delete("/api/budgets", params={"category": "drink/dessert"}, headers=amir)
    assert res.status_code == 204


@pytest.mark.parametrize("name", ["Refund", "Transfer", "BNPL", "Salary", "123"])
def test_categories_that_cannot_have_a_budget_are_refused(api, amir, name):
    res = api.put("/api/budgets", json={"category": name, "limit_sen": 100}, headers=amir)
    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "invalid_budget_category"


@pytest.mark.parametrize("limit", [0, -5, 10.5, "100", None])
def test_a_limit_must_be_positive_whole_sen(api, amir, limit):
    res = api.put("/api/budgets", json={"category": "Food", "limit_sen": limit}, headers=amir)
    assert res.status_code == 422


def test_status_shows_spent_state_and_pace(api, amir):
    api.put("/api/budgets", json={"category": "Food", "limit_sen": 10000}, headers=amir)
    spend(api, amir, "2026-03-02", 8000)
    spend(api, amir, "2026-03-03", 1200, "Transport")
    body = api.get("/api/budgets/status", params={"month": MONTH}, headers=amir).json()
    (food,) = body["items"]
    assert (food["spent_sen"], food["state"], food["percent"]) == (8000, "near", 0.8)
    assert food["projected_sen"] == 8000 * 31 // 15
    assert food["projected_state"] == "over"
    assert body["unbudgeted_spend_sen"] == 1200
    assert body["month_spend_sen"] == 9200


def test_status_needs_a_valid_month(api, amir):
    assert (
        api.get("/api/budgets/status", params={"month": "2026-13"}, headers=amir).status_code == 422
    )


def test_suggest_stores_nothing(api, amir, fake_db):
    spend(api, amir, "2026-02-02", 8000)
    body = {"date": "2026-02-01", "amount_sen": 50000, "type": "income", "category": "Salary"}
    api.post("/api/transactions", json=body, headers=amir)
    res = api.post("/api/budgets/suggest", json={}, headers=amir)
    assert res.status_code == 200
    out = res.json()
    assert out["month"] == MONTH
    assert out["income_basis"] == "average"
    assert out["income_sen"] == 50000
    assert out["pool_sen"] == 45000
    assert [(i["category"], i["limit_sen"]) for i in out["items"]] == [("Food", 45000)]
    assert fake_db.rows("budgets") == []


def test_one_users_budgets_are_invisible_and_untouchable_by_another(api, amir, siti):
    api.put("/api/budgets", json={"category": "Food", "limit_sen": 10000}, headers=amir)
    spend(api, amir, "2026-03-02", 4000)
    assert api.get("/api/budgets", headers=siti).json()["budgets"] == []
    assert api.delete("/api/budgets", params={"category": "Food"}, headers=siti).status_code == 404
    siti_status = api.get("/api/budgets/status", params={"month": MONTH}, headers=siti).json()
    assert siti_status["items"] == [] and siti_status["month_spend_sen"] == 0
    api.put("/api/budgets", json={"category": "Food", "limit_sen": 777}, headers=siti)
    mine = api.get("/api/budgets", headers=amir).json()["budgets"]
    assert mine[0]["limit_sen"] == 10000
    siti_suggest = api.post("/api/budgets/suggest", json={}, headers=siti).json()
    assert siti_suggest["items"] == [] and siti_suggest["income_sen"] == 0


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/budgets"),
        ("put", "/api/budgets"),
        ("delete", "/api/budgets?category=Food"),
        ("get", "/api/budgets/status?month=2026-03"),
        ("post", "/api/budgets/suggest"),
    ],
)
def test_every_budget_route_needs_a_session(api, method, path):
    assert api.request(method.upper(), path, json={}).status_code == 401
