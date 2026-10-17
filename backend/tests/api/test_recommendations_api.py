"""GET /api/recommendations and /api/alerts (WP15): user-scoped, need a session."""

from datetime import date

import pytest

from app.api.deps import get_today


@pytest.fixture(autouse=True)
def pinned_today(api):
    api.app.dependency_overrides[get_today] = lambda: date(2026, 3, 10)


def spend(api, headers, day, amount, category="Food"):
    body = {"date": day, "amount_sen": amount, "type": "expense", "category": category}
    assert api.post("/api/transactions", json=body, headers=headers).status_code == 201


def test_an_over_budget_category_is_an_alert_with_its_figures(api, amir):
    api.put("/api/budgets", json={"category": "Food", "limit_sen": 10_000}, headers=amir)
    spend(api, amir, "2026-03-02", 12_000)
    recs = api.get("/api/recommendations", headers=amir).json()
    rules = [r["rule"] for r in recs["items"]]
    assert "budget_over" in rules and "forecast_locked" in rules
    assert len(recs["checked_rules"]) == 9
    over = next(r for r in recs["items"] if r["rule"] == "budget_over")
    assert {s["value"] for s in over["sources"]} == {12_000, 10_000}
    alerts = api.get("/api/alerts", headers=amir).json()["items"]
    assert [a["rule"] for a in alerts] == ["budget_over"]
    assert all(a["is_alert"] for a in alerts)


def test_another_users_data_never_feeds_the_rules(api, amir, siti):
    api.put("/api/budgets", json={"category": "Food", "limit_sen": 10_000}, headers=amir)
    spend(api, amir, "2026-03-02", 12_000)
    assert api.get("/api/alerts", headers=siti).json()["items"] == []
    siti_rules = {r["rule"] for r in api.get("/api/recommendations", headers=siti).json()["items"]}
    assert siti_rules == {"forecast_locked"}


@pytest.mark.parametrize("path", ["/api/recommendations", "/api/alerts"])
def test_recommendations_need_a_session(api, path):
    assert api.get(path).status_code == 401
