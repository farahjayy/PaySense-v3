"""GET /api/insights/spending (WP14): user-scoped, needs a session."""


def post(api, headers, day, amount, category="Food", kind="expense"):
    body = {"date": day, "amount_sen": amount, "type": kind, "category": category}
    assert api.post("/api/transactions", json=body, headers=headers).status_code == 201


def test_insights_for_a_month_with_a_comparison(api, amir):
    post(api, amir, "2026-01-02", 100_000, "Allowance", "income")
    post(api, amir, "2026-01-05", 20_000)
    post(api, amir, "2026-02-02", 100_000, "Allowance", "income")
    post(api, amir, "2026-02-05", 30_000)
    res = api.get("/api/insights/spending", params={"month": "2026-02"}, headers=amir)
    assert res.status_code == 200
    body = res.json()
    assert body["previous_month"] == "2026-01"
    assert body["spend_sen"] == 30_000 and body["left_over_sen"] == 70_000
    assert body["savings_rate"] == 0.7
    assert body["headline_rule"] == "category_up"
    assert body["movers"][0]["category"] == "Food"


def test_another_users_ledger_is_not_used(api, amir, siti):
    post(api, amir, "2026-02-05", 30_000)
    body = api.get("/api/insights/spending", params={"month": "2026-02"}, headers=siti).json()
    assert body["spend_sen"] == 0 and body["categories"] == []
    assert body["headline_rule"] == "no_data"


def test_the_month_is_validated(api, amir):
    res = api.get("/api/insights/spending", params={"month": "02-2026"}, headers=amir)
    assert res.status_code == 422


def test_insights_need_a_session(api):
    assert api.get("/api/insights/spending", params={"month": "2026-02"}).status_code == 401
