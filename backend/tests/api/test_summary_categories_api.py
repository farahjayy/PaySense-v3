"""GET /api/summary/categories: where one month's money went (ADR D-45)."""

import pytest


def post(api, headers, **overrides):
    body = {
        "date": "2026-06-10",
        "amount_sen": 1000,
        "type": "expense",
        "category": "Food",
        "description": "Lunch",
    } | overrides
    res = api.post("/api/transactions", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def categories(api, headers, month="2026-06"):
    return api.get("/api/summary/categories", params={"month": month}, headers=headers)


def test_a_new_user_gets_zeros_and_no_categories(api, amir):
    res = categories(api, amir)

    assert res.status_code == 200
    assert res.json() == {
        "month": "2026-06",
        "income_sen": 0,
        "spend_sen": 0,
        "gross_spend_sen": 0,
        "refund_sen": 0,
        "savings_sen": 0,
        "categories": [],
    }


def test_spending_is_grouped_by_category_for_the_asked_month_only(api, amir):
    post(api, amir, amount_sen=1500, category="Food")
    post(api, amir, amount_sen=2500, category="Food")
    post(api, amir, amount_sen=6000, category="Transport")
    post(api, amir, date="2026-05-31", amount_sen=9999, category="Shopping")
    post(api, amir, type="income", category="Allowance", amount_sen=100000)

    body = categories(api, amir).json()

    assert body["income_sen"] == 100000
    assert body["gross_spend_sen"] == 10000
    assert body["categories"] == [
        {"category": "Transport", "spend_sen": 6000, "count": 1, "share": 0.6},
        {"category": "Food", "spend_sen": 4000, "count": 2, "share": 0.4},
    ]


def test_transfers_refunds_and_savings_are_handled_like_the_month_summary(api, amir):
    post(api, amir, amount_sen=30000, category="Food")
    post(api, amir, amount_sen=5000, type="income", category="Refund")
    post(api, amir, amount_sen=99999, category="Transfer")
    post(api, amir, amount_sen=7000, type="savings", category="Saving")

    body = categories(api, amir).json()
    summary = api.get("/api/summary/months", headers=amir).json()["months"][0]

    assert body["spend_sen"] == summary["spend_sen"] == 25000
    assert body["refund_sen"] == 5000
    assert body["savings_sen"] == 7000
    assert [c["category"] for c in body["categories"]] == ["Food"]


def test_a_bnpl_plan_payment_is_its_own_row(api, amir):
    # A limit smaller than the price makes the plan log the part paid at checkout as a BNPL row.
    limit = api.put("/api/provider-limits/spaylater", json={"limit_sen": 10000}, headers=amir)
    assert limit.status_code == 200, limit.text
    plan = api.post(
        "/api/plans",
        json={
            "provider": "spaylater",
            "item_name": "Camera",
            "purchase_date": "2026-06-10",
            "num_installments": 3,
            "total_price_sen": 30000,
        },
        headers=amir,
    )
    assert plan.status_code == 201, plan.text

    rows = {c["category"]: c for c in categories(api, amir).json()["categories"]}

    assert "BNPL" in rows and rows["BNPL"]["spend_sen"] > 0


def test_each_user_sees_only_their_own_spending(api, amir, siti):
    post(api, amir, amount_sen=5555, category="Food")
    post(api, siti, amount_sen=111, category="Shopping")

    mine = categories(api, amir).json()
    hers = categories(api, siti).json()

    assert [(c["category"], c["spend_sen"]) for c in mine["categories"]] == [("Food", 5555)]
    assert [(c["category"], c["spend_sen"]) for c in hers["categories"]] == [("Shopping", 111)]


def test_it_needs_a_login(api):
    assert api.get("/api/summary/categories", params={"month": "2026-06"}).status_code == 401


@pytest.mark.parametrize("month", ["2026-13", "2026-6", "June", "2026-06-01", "1999-12", "2101-01"])
def test_a_month_that_is_not_a_real_one_is_refused_with_the_envelope(api, amir, month):
    res = categories(api, amir, month=month)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "validation_error"


def test_the_month_is_required(api, amir):
    assert api.get("/api/summary/categories", headers=amir).status_code == 422
