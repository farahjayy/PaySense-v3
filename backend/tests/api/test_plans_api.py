from datetime import date

import pytest

from app.api.deps import get_today

TODAY = date(2026, 9, 26)


@pytest.fixture(autouse=True)
def fixed_today(api):
    api.app.dependency_overrides[get_today] = lambda: TODAY
    yield
    api.app.dependency_overrides.pop(get_today, None)


def pay_later(**overrides):
    return {
        "provider": "spaylater",
        "item_name": "Phone",
        "purchase_date": "2026-09-25",
        "num_installments": 3,
        "total_price_sen": 30000,
    } | overrides


def manual(**overrides):
    return {
        "provider": "other",
        "item_name": "Laptop",
        "provider_label": "Grab PayLater",
        "purchase_date": "2026-09-25",
        "first_payment_date": "2026-10-03",
        "num_installments": 3,
        "total_payable_sen": 10001,
    } | overrides


def create(api, headers, body):
    res = api.post("/api/plans", json=body, headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def set_limit(api, headers, provider, sen):
    res = api.put(f"/api/provider-limits/{provider}", json={"limit_sen": sen}, headers=headers)
    assert res.status_code == 200, res.text


def limits(api, headers):
    return {r["provider"]: r for r in api.get("/api/provider-limits", headers=headers).json()}


def txns(api, headers):
    res = api.get("/api/transactions?start=2026-01-01&end=2026-12-31", headers=headers)
    return res.json()["transactions"]


# ------------------------------------------------------------------ preview
def test_preview_shows_the_schedule_and_stores_nothing(api, amir):
    res = api.post("/api/plans/preview", json=pay_later(), headers=amir)

    assert res.status_code == 200
    preview = res.json()
    assert (preview["financed_sen"], preview["upfront_sen"]) == (30000, 0)
    assert preview["total_payable_sen"] == 30000 and preview["cash_at_purchase_sen"] == 0
    assert preview["first_payment_date"] == "2026-10-25"
    assert [(i["seq"], i["due_date"], i["amount_sen"]) for i in preview["installments"]] == [
        (1, "2026-10-25", 10000),
        (2, "2026-11-25", 10000),
        (3, "2026-12-25", 10000),
    ]
    assert preview["limit_known"] is False and preview["remaining_limit_sen"] is None
    assert preview["schedule_source"] == "provider_rule"
    assert api.get("/api/plans", headers=amir).json() == []
    assert txns(api, amir) == []


def test_preview_applies_the_monthly_fee(api, amir):
    res = api.post(
        "/api/plans/preview",
        json=pay_later(total_price_sen=14762, num_installments=6, monthly_fee_rate_pct=1.5),
        headers=amir,
    )

    assert res.json()["total_payable_sen"] == 16091
    assert res.json()["installments"][-1]["amount_sen"] == 2686


def test_the_authors_example_limit_200_price_300_pay_100_at_checkout(api, amir):
    set_limit(api, amir, "spaylater", 20000)

    res = api.post("/api/plans/preview", json=pay_later(num_installments=2), headers=amir)

    preview = res.json()
    assert (preview["financed_sen"], preview["upfront_sen"]) == (20000, 10000)
    assert preview["total_price_sen"] == 30000
    assert preview["cash_at_purchase_sen"] == 10000
    assert preview["limit_known"] is True and preview["remaining_limit_sen"] == 20000
    assert [i["amount_sen"] for i in preview["installments"]] == [10000, 10000]


def test_an_existing_plan_uses_up_part_of_the_limit(api, amir):
    set_limit(api, amir, "spaylater", 50000)
    create(api, amir, pay_later(total_price_sen=20000, num_installments=2))

    res = api.post(
        "/api/plans/preview",
        json=pay_later(total_price_sen=40000, num_installments=2),
        headers=amir,
    )

    assert res.json()["remaining_limit_sen"] == 30000
    assert (res.json()["financed_sen"], res.json()["upfront_sen"]) == (30000, 10000)


def test_atome_preview_marks_the_checkout_instalment(api, amir):
    res = api.post("/api/plans/preview", json=pay_later(provider="atome"), headers=amir)

    first = res.json()["installments"][0]
    assert first["paid_at_checkout"] is True
    assert res.json()["cash_at_purchase_sen"] == 10000


def test_manual_provider_preview_uses_exactly_what_was_typed(api, amir):
    res = api.post("/api/plans/preview", json=manual(), headers=amir)

    preview = res.json()
    assert preview["schedule_source"] == "manual" and preview["provider_label"] == "Grab PayLater"
    assert [i["amount_sen"] for i in preview["installments"]] == [3333, 3333, 3335]
    assert preview["first_payment_date"] == "2026-10-03"
    assert preview["monthly_fee_rate_pct"] == 0


@pytest.mark.parametrize(
    ("body", "code"),
    [
        (pay_later(instalment_sen=100), "manual_fields_not_allowed"),
        (manual(provider_label=None), "provider_label_required"),
        (manual(first_payment_date=None), "first_payment_date_required"),
        (manual(instalment_sen=100), "amount_required"),  # both amounts given
        (manual(total_payable_sen=None), "amount_required"),  # neither given
        (manual(total_price_sen=500), "price_not_allowed"),
        (pay_later(total_price_sen=2), "amount_too_small"),
    ],
)
def test_business_rule_errors_carry_a_code(api, amir, body, code):
    res = api.post("/api/plans/preview", json=body, headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == code


@pytest.mark.parametrize(
    "bad",
    [
        {"total_price_sen": 300.5},
        {"total_price_sen": 0},
        {"num_installments": 0},
        {"num_installments": 37},
        {"monthly_fee_rate_pct": -1},
        {"monthly_fee_rate_pct": 99},
        {"provider": "grab_paylater"},
        {"purchase_date": "25/09/2026"},
        {"surprise": 1},
    ],
)
def test_malformed_input_is_a_validation_error(api, amir, bad):
    res = api.post("/api/plans/preview", json=pay_later(**bad), headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "validation_error"


# ------------------------------------------------------------------ create
def test_create_stores_the_plan_with_its_derived_fields(api, amir):
    plan = create(api, amir, pay_later())

    assert plan["item_name"] == "Phone" and plan["provider"] == "spaylater"
    assert plan["status"] == "active"
    assert (plan["paid_count"], plan["remaining_count"]) == (0, 3)
    assert plan["installment_amount_sen"] == 10000 and plan["total_payable_sen"] == 30000
    assert plan["next_due_date"] == "2026-10-25"
    assert [i["seq"] for i in plan["installments"]] == [1, 2, 3]
    assert not any(i["is_paid"] for i in plan["installments"])
    assert api.get("/api/plans", headers=amir).json()[0]["id"] == plan["id"]
    assert api.get(f"/api/plans/{plan['id']}", headers=amir).json()["id"] == plan["id"]
    assert txns(api, amir) == []  # nothing is paid at checkout with SPayLater


def test_create_logs_the_excess_over_the_limit_as_a_checkout_payment(api, amir):
    set_limit(api, amir, "spaylater", 20000)

    plan = create(api, amir, pay_later(num_installments=2))

    assert (plan["financed_sen"], plan["upfront_sen"], plan["total_price_sen"]) == (
        20000,
        10000,
        30000,
    )
    (payment,) = txns(api, amir)
    assert payment["amount_sen"] == 10000 and payment["date"] == "2026-09-25"
    assert payment["description"] == "SPayLater checkout payment — Phone"
    assert payment["is_bnpl"] is True and payment["bnpl_plan_id"] == plan["id"]
    assert limits(api, amir)["spaylater"]["used_sen"] == 20000


def test_create_an_atome_plan_pays_the_first_instalment_at_checkout(api, amir):
    plan = create(api, amir, pay_later(provider="atome"))

    assert (plan["paid_count"], plan["remaining_count"]) == (1, 2)
    assert plan["installments"][0]["is_paid"] is True
    assert plan["installments"][0]["paid_date"] == "2026-09-25"
    (payment,) = txns(api, amir)
    assert payment["amount_sen"] == 10000
    assert payment["description"] == "Atome instalment 1/3 — Phone"


def test_create_a_manual_other_provider_plan(api, amir):
    plan = create(api, amir, manual())

    assert plan["schedule_source"] == "manual" and plan["provider_label"] == "Grab PayLater"
    assert [i["amount_sen"] for i in plan["installments"]] == [3333, 3333, 3335]
    assert plan["total_payable_sen"] == 10001
    assert txns(api, amir) == []


def test_create_refuses_when_the_limit_is_used_up_and_stores_nothing(api, amir):
    set_limit(api, amir, "spaylater", 20000)
    create(api, amir, pay_later(total_price_sen=20000, num_installments=2))

    res = api.post("/api/plans", json=pay_later(), headers=amir)

    assert res.status_code == 422 and res.json()["detail"]["code"] == "limit_exhausted"
    assert len(api.get("/api/plans", headers=amir).json()) == 1


def test_an_unpaid_instalment_in_the_past_makes_a_plan_overdue(api, amir):
    plan = create(api, amir, pay_later(first_payment_date="2026-09-01"))

    assert plan["status"] == "overdue"


def test_plans_are_listed_newest_first(api, amir):
    first = create(api, amir, pay_later(item_name="First"))
    second = create(api, amir, pay_later(item_name="Second"))

    listed = api.get("/api/plans", headers=amir).json()

    assert [p["id"] for p in listed] == [second["id"], first["id"]]


# ------------------------------------------------------------------ rename / delete
def test_rename_updates_the_plan_and_the_payments_it_logged(api, amir):
    plan = create(api, amir, pay_later(provider="atome"))

    res = api.patch(f"/api/plans/{plan['id']}", json={"item_name": "Phone Case"}, headers=amir)

    assert res.status_code == 200 and res.json()["item_name"] == "Phone Case"
    assert txns(api, amir)[0]["description"] == "Atome instalment 1/3 — Phone Case"


@pytest.mark.parametrize("name", ["", "   ", "x" * 121])
def test_rename_validates_the_name(api, amir, name):
    plan = create(api, amir, pay_later())

    res = api.patch(f"/api/plans/{plan['id']}", json={"item_name": name}, headers=amir)

    assert res.status_code == 422


def test_delete_keeps_logged_payments_by_default(api, amir):
    plan = create(api, amir, pay_later(provider="atome"))

    res = api.delete(f"/api/plans/{plan['id']}", headers=amir)

    assert res.status_code == 204
    assert api.get(f"/api/plans/{plan['id']}", headers=amir).status_code == 404
    (kept,) = txns(api, amir)
    assert kept["bnpl_plan_id"] is None  # the money did leave; the plan no longer owns the row


def test_delete_can_remove_the_logged_payments_too(api, amir):
    plan = create(api, amir, pay_later(provider="atome"))

    api.delete(f"/api/plans/{plan['id']}?keep_payments=false", headers=amir)

    assert txns(api, amir) == []


# ------------------------------------------------------------------ paying
def test_paying_an_instalment_marks_it_and_logs_the_payment(api, amir):
    plan = create(api, amir, pay_later())

    res = api.post(f"/api/plans/{plan['id']}/installments/1/pay", json={}, headers=amir)

    assert res.status_code == 200
    assert res.json() == {
        "seq": 1,
        "due_date": "2026-10-25",
        "amount_sen": 10000,
        "is_paid": True,
        "paid_date": "2026-09-26",  # defaults to today
    }
    (payment,) = txns(api, amir)
    assert payment["amount_sen"] == 10000 and payment["date"] == "2026-09-26"
    refreshed = api.get(f"/api/plans/{plan['id']}", headers=amir).json()
    assert (refreshed["paid_count"], refreshed["next_due_date"]) == (1, "2026-11-25")
    assert limits(api, amir)["spaylater"]["used_sen"] == 20000


def test_paying_on_a_given_date(api, amir):
    plan = create(api, amir, pay_later())

    res = api.post(
        f"/api/plans/{plan['id']}/installments/1/pay",
        json={"paid_date": "2026-09-20"},
        headers=amir,
    )

    assert res.json()["paid_date"] == "2026-09-20"


def test_paying_twice_is_a_conflict_and_logs_once(api, amir):
    plan = create(api, amir, pay_later())
    api.post(f"/api/plans/{plan['id']}/installments/1/pay", json={}, headers=amir)

    res = api.post(f"/api/plans/{plan['id']}/installments/1/pay", json={}, headers=amir)

    assert res.status_code == 409 and res.json()["detail"]["code"] == "already_paid"
    assert len(txns(api, amir)) == 1


def test_paying_an_unknown_instalment_is_a_404(api, amir):
    plan = create(api, amir, pay_later())

    res = api.post(f"/api/plans/{plan['id']}/installments/9/pay", json={}, headers=amir)

    assert res.status_code == 404 and res.json()["detail"]["code"] == "installment_not_found"


def test_paying_in_the_future_is_refused(api, amir):
    plan = create(api, amir, pay_later())

    res = api.post(
        f"/api/plans/{plan['id']}/installments/1/pay",
        json={"paid_date": "2026-10-01"},
        headers=amir,
    )

    assert res.status_code == 422 and res.json()["detail"]["code"] == "paid_date_in_future"


def test_bulk_pay_marks_several_in_order(api, amir):
    plan = create(api, amir, pay_later())

    res = api.post(f"/api/plans/{plan['id']}/pay", json={"seqs": [2, 1]}, headers=amir)

    assert res.status_code == 200
    assert [i["seq"] for i in res.json()] == [1, 2]
    assert len(txns(api, amir)) == 2


def test_bulk_pay_checks_everything_before_paying_anything(api, amir):
    plan = create(api, amir, pay_later())
    api.post(f"/api/plans/{plan['id']}/installments/1/pay", json={}, headers=amir)

    already = api.post(f"/api/plans/{plan['id']}/pay", json={"seqs": [2, 1]}, headers=amir)
    missing = api.post(f"/api/plans/{plan['id']}/pay", json={"seqs": [2, 9]}, headers=amir)

    assert already.status_code == 409 and already.json()["detail"]["code"] == "already_paid"
    assert (
        missing.status_code == 404 and missing.json()["detail"]["code"] == "installment_not_found"
    )
    assert len(txns(api, amir)) == 1


def test_bulk_pay_needs_at_least_one_instalment(api, amir):
    plan = create(api, amir, pay_later())

    assert (
        api.post(f"/api/plans/{plan['id']}/pay", json={"seqs": []}, headers=amir).status_code == 422
    )


def test_paying_every_instalment_completes_the_plan(api, amir):
    plan = create(api, amir, pay_later())

    api.post(f"/api/plans/{plan['id']}/pay", json={"seqs": [1, 2, 3]}, headers=amir)

    assert api.get(f"/api/plans/{plan['id']}", headers=amir).json()["status"] == "completed"
    assert limits(api, amir)["spaylater"]["used_sen"] == 0


# ------------------------------------------------------------------ bills
def test_bills_group_every_plans_instalments_by_month(api, amir):
    create(api, amir, pay_later(item_name="Phone"))
    create(api, amir, pay_later(item_name="Earbuds", total_price_sen=6000, num_installments=2))

    res = api.get("/api/bills", headers=amir)

    assert res.status_code == 200
    months = {m["month"]: m for m in res.json()["months"]}
    assert set(months) == {"2026-10", "2026-11", "2026-12"}
    assert months["2026-10"]["total_due_sen"] == 13000
    assert months["2026-12"]["total_due_sen"] == 10000
    assert months["2026-10"]["fully_paid"] is False
    assert {i["item_name"] for i in months["2026-10"]["items"]} == {"Phone", "Earbuds"}
    assert months["2026-10"]["items"][0]["provider_label"] == "SPayLater"


def test_bills_are_empty_without_plans(api, amir):
    assert api.get("/api/bills", headers=amir).json() == {"months": []}


# ------------------------------------------------------------------ isolation and auth
def test_one_users_plans_are_invisible_and_untouchable_by_another(api, amir, siti):
    plan = create(api, amir, pay_later(provider="atome"))
    pid = plan["id"]

    assert api.get("/api/plans", headers=siti).json() == []
    assert api.get("/api/bills", headers=siti).json() == {"months": []}
    responses = [
        api.get(f"/api/plans/{pid}", headers=siti),
        api.patch(f"/api/plans/{pid}", json={"item_name": "Hijacked"}, headers=siti),
        api.delete(f"/api/plans/{pid}", headers=siti),
        api.post(f"/api/plans/{pid}/installments/2/pay", json={}, headers=siti),
        api.post(f"/api/plans/{pid}/pay", json={"seqs": [2]}, headers=siti),
    ]
    assert [r.status_code for r in responses] == [404] * 5
    assert {r.json()["detail"]["code"] for r in responses} == {"plan_not_found"}
    intact = api.get(f"/api/plans/{pid}", headers=amir).json()
    assert intact["item_name"] == "Phone" and intact["paid_count"] == 1
    assert len(txns(api, amir)) == 1 and txns(api, siti) == []


def test_another_users_plans_do_not_use_up_my_limit(api, amir, siti):
    set_limit(api, siti, "spaylater", 20000)
    create(api, amir, pay_later(total_price_sen=20000, num_installments=2))

    assert limits(api, siti)["spaylater"]["used_sen"] == 0
    preview = api.post("/api/plans/preview", json=pay_later(num_installments=2), headers=siti)
    assert preview.json()["remaining_limit_sen"] == 20000


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/api/plans/preview"),
        ("post", "/api/plans"),
        ("get", "/api/plans"),
        ("get", "/api/plans/x"),
        ("patch", "/api/plans/x"),
        ("delete", "/api/plans/x"),
        ("post", "/api/plans/x/installments/1/pay"),
        ("post", "/api/plans/x/pay"),
        ("get", "/api/bills"),
    ],
)
def test_every_route_requires_login(api, method, path):
    assert getattr(api, method)(path).status_code == 401
