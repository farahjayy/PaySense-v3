"""GET /api/insights/bills (WP13): user-scoped, needs a session."""

from datetime import date

import pytest

from app.api.deps import get_today


@pytest.fixture(autouse=True)
def pinned_today(api):
    api.app.dependency_overrides[get_today] = lambda: date(2026, 3, 10)


def bill(api, headers, name, amount, anchor):
    body = {"kind": "bill", "name": name, "amount_sen": amount, "cadence": "monthly",
            "anchor_date": anchor}  # fmt: skip
    assert api.post("/api/recurring-items", json=body, headers=headers).status_code == 201


def plan(api, headers, provider, item, price, day):
    body = {"provider": provider, "item_name": item, "purchase_date": day,
            "num_installments": 3, "total_price_sen": price}  # fmt: skip
    assert api.post("/api/plans", json=body, headers=headers).status_code == 201


def test_bills_collisions_and_upcoming_for_the_caller(api, amir):
    bill(api, amir, "Rent bilik", 35000, "2026-01-15")
    plan(api, amir, "spaylater", "Phone", 79900, "2026-02-14")  # first due 14 March
    res = api.get("/api/insights/bills", headers=amir)
    assert res.status_code == 200
    body = res.json()
    assert body["recurring"]["count"] == 1
    assert body["recurring"]["monthly_total_sen"] == 35000
    names = [(i["name"], i["due_date"]) for i in body["upcoming"]]
    assert ("Phone", "2026-03-14") in names and ("Rent bilik", "2026-03-15") in names
    (collision,) = body["collisions"]
    assert {i["name"] for i in collision["items"]} == {"Phone", "Rent bilik"}


def test_another_users_bills_are_not_seen(api, amir, siti):
    bill(api, amir, "Rent bilik", 35000, "2026-01-15")
    plan(api, amir, "atome", "Shoes", 18000, "2026-03-11")
    body = api.get("/api/insights/bills", headers=siti).json()
    assert body["recurring"]["count"] == 0
    assert body["upcoming"] == [] and body["collisions"] == []


def test_bills_need_a_session(api):
    assert api.get("/api/insights/bills").status_code == 401
