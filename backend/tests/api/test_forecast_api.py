from datetime import date, timedelta

import pytest

from app.api.deps import get_today
from app.api.forecast import get_forecaster
from app.db import transactions as transactions_repo
from app.db import users
from app.engines.forecasting.models import MovingAverage

TODAY = date(2025, 5, 12)  # a Monday


@pytest.fixture(autouse=True)
def pinned(api):
    api.app.dependency_overrides[get_today] = lambda: TODAY
    api.app.dependency_overrides[get_forecaster] = lambda: MovingAverage(8)
    yield
    api.app.dependency_overrides.clear()


def user_id(fake_db, username):
    return users.get_by_username(fake_db, username)["id"]


def txn(day, amount, kind="expense", category="Food", description="Kedai makan"):
    return {
        "date": day.isoformat(),
        "amount_sen": amount,
        "type": kind,
        "category": category,
        "description": description,
    }


def fill(fake_db, username, income=200000, weekly=6000, first=date(2025, 1, 6)):
    rows, day = [], first
    while day < TODAY:
        rows.append(txn(day, weekly))
        day += timedelta(days=7)
    rows += [
        txn(date(2025, m, 1), income, "income", "Allowance", "Duit belanja") for m in range(1, 6)
    ]
    transactions_repo.bulk_create(fake_db, user_id(fake_db, username), rows, source="seed")


def test_unauthenticated_requests_are_refused(api):
    assert api.get("/api/forecast").status_code == 401


def test_a_new_user_with_no_history_is_locked(api, amir):
    res = api.get("/api/forecast", headers=amir)

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "locked" and body["simulation"] is None
    assert body["band"] is None and body["health_score"] is None
    assert body["months_of_history"] == 0


def test_a_user_with_enough_history_gets_a_forecast_in_integer_sen(api, fake_db, amir):
    fill(fake_db, "amir")

    body = api.get("/api/forecast", headers=amir).json()

    assert body["status"] == "ok" and body["as_of"] == "2025-05-12"
    assert body["model"] == "ma8"
    sim = body["simulation"]
    assert sim["months"] == ["2025-05", "2025-06", "2025-07"]
    for key in ("monthly_margin_p50_sen", "cumulative_margin_p10_sen", "cumulative_margin_p90_sen"):
        assert all(isinstance(v, int) for v in sim[key]) and len(sim[key]) == 3
    assert 0 <= sim["p_shortfall"] <= 1
    assert body["band"] in {"Safe", "Caution", "At Risk"} and 0 <= body["health_score"] <= 100


def test_the_forecast_is_stable_when_the_page_is_reloaded(api, fake_db, amir):
    fill(fake_db, "amir")

    assert (
        api.get("/api/forecast", headers=amir).json()
        == api.get("/api/forecast", headers=amir).json()
    )


def test_one_users_ledger_never_affects_another_users_forecast(api, fake_db, amir, siti):
    fill(fake_db, "amir", income=300000)

    mine = api.get("/api/forecast", headers=amir).json()
    theirs = api.get("/api/forecast", headers=siti).json()

    assert mine["status"] == "ok" and theirs["status"] == "locked"
    assert theirs["simulation"] is None and theirs["months_of_history"] == 0


def test_two_users_with_different_ledgers_get_different_forecasts(api, fake_db, amir, siti):
    fill(fake_db, "amir", income=300000)
    fill(fake_db, "siti", income=20000, weekly=30000)

    rich = api.get("/api/forecast", headers=amir).json()
    stretched = api.get("/api/forecast", headers=siti).json()

    assert rich["health_score"] > stretched["health_score"]


def test_confirmed_recurring_items_change_the_forecast(api, fake_db, amir):
    fill(fake_db, "amir", income=20000)  # logged income is tiny...
    before = api.get("/api/forecast", headers=amir).json()["simulation"][
        "cumulative_margin_p50_sen"
    ]

    api.post(
        "/api/recurring-items",
        json={
            "kind": "income",
            "name": "Biasiswa",
            "amount_sen": 150000,
            "cadence": "monthly",
            "anchor_date": "2025-05-20",
            "origin": "detected",
        },
        headers=amir,
    )
    after = api.get("/api/forecast", headers=amir).json()["simulation"]["cumulative_margin_p50_sen"]

    assert after[-1] > before[-1]


def test_suggestions_are_listed_for_the_users_own_ledger_only(api, fake_db, amir, siti):
    rows = [
        txn(date(2025, m, 5), 45000, category="Bills", description="Sewa bilik")
        for m in (1, 2, 3, 4)
    ]
    transactions_repo.bulk_create(fake_db, user_id(fake_db, "amir"), rows, source="seed")

    mine = api.get("/api/recurring-items/suggestions", headers=amir).json()
    theirs = api.get("/api/recurring-items/suggestions", headers=siti).json()

    assert [s["name"] for s in mine] == ["sewa bilik"]
    assert mine[0]["cadence"] == "monthly" and mine[0]["amount_sen"] == 45000
    assert theirs == []


def test_a_confirmed_suggestion_is_not_suggested_again(api, fake_db, amir):
    rows = [
        txn(date(2025, m, 5), 45000, category="Bills", description="Sewa bilik")
        for m in (1, 2, 3, 4)
    ]
    transactions_repo.bulk_create(fake_db, user_id(fake_db, "amir"), rows, source="seed")
    api.post(
        "/api/recurring-items",
        json={
            "kind": "bill",
            "name": "Sewa bilik",
            "amount_sen": 45000,
            "cadence": "monthly",
            "anchor_date": "2025-04-05",
            "origin": "detected",
        },
        headers=amir,
    )

    assert api.get("/api/recurring-items/suggestions", headers=amir).json() == []


def test_suggestions_require_authentication(api):
    assert api.get("/api/recurring-items/suggestions").status_code == 401


def test_an_unknown_origin_is_refused(api, amir):
    res = api.post(
        "/api/recurring-items",
        json={"kind": "bill", "name": "x", "amount_sen": 100, "cadence": "monthly",
              "anchor_date": "2025-05-01", "origin": "guessed"},
        headers=amir,
    )  # fmt: skip

    assert res.status_code == 422
