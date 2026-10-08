"""P1 repository contract against the REAL Supabase project: `uv run pytest -m integration`.

Mirrors the fake-backed unit tests for the behaviours where the fake could be wrong: composite
foreign keys, the plan-financing check constraint, unique (plan_id, seq), on delete set null,
the atomic provider-limit upsert, and the conditional mark-paid flip. Needs backend/.env and
migration 0001 applied; skips otherwise.
"""

from datetime import date

import pytest
from postgrest import APIError

from app.db import plans as plans_repo
from app.db import provider_limits, recurring_items, transactions
from app.db.base import ScopedTable
from app.domain.schedule import build_manual_schedule, build_schedule

pytestmark = pytest.mark.integration

FK_VIOLATION = "23503"
UNIQUE_VIOLATION = "23505"
CHECK_VIOLATION = "23514"
PURCHASE = date(2026, 3, 5)


def make_plan(db, user_id, *, provider="atome", price=30000, upfront=0, count=3):
    financed = price - upfront
    if provider == "other":
        instalments = build_manual_schedule(PURCHASE, count, total_payable_sen=financed)
        source, label = "manual", "Other provider"
    else:
        instalments = build_schedule(provider, financed, 0, count, PURCHASE)
        source, label = "provider_rule", provider.title()
    plan = {
        "item_name": "Phone",
        "provider": provider,
        "provider_label": label,
        "schedule_source": source,
        "total_price_sen": price,
        "financed_sen": financed,
        "upfront_sen": upfront,
        "monthly_fee_rate_pct": 0,
        "num_installments": count,
        "purchase_date": PURCHASE,
        "first_payment_date": instalments[0].due_date,
    }
    return plans_repo.create_plan(db, user_id, plan, instalments)


def test_a_plan_round_trips_with_its_schedule_and_checkout_payments(db, two_users):
    a = two_users[0]["id"]

    created = make_plan(db, a, provider="atome", upfront=3000)

    assert [i["amount_sen"] for i in created["installments"]] == [9000, 9000, 9000]
    assert created["installments"][0]["is_paid"] is True
    assert sorted(t["amount_sen"] for t in transactions.list_for_plan(db, a, created["id"])) == [
        3000,
        9000,
    ]


def test_the_financing_check_constraint_holds_in_the_database(db, two_users):
    a = two_users[0]["id"]
    row = {
        "item_name": "Phone",
        "provider": "atome",
        "provider_label": "Atome",
        "total_price_sen": 30000,
        "financed_sen": 20000,
        "upfront_sen": 5000,  # 20000 + 5000 != 30000
        "num_installments": 3,
        "purchase_date": "2026-03-05",
        "first_payment_date": "2026-03-05",
    }

    with pytest.raises(APIError) as err:
        ScopedTable(db, "bnpl_plans").insert(a, row)

    assert err.value.code == CHECK_VIOLATION


def test_instalment_numbers_are_unique_within_a_plan(db, two_users):
    a = two_users[0]["id"]
    created = make_plan(db, a, provider="spaylater")

    with pytest.raises(APIError) as err:
        ScopedTable(db, "bnpl_installments").insert(
            a,
            {"plan_id": created["id"], "seq": 1, "due_date": "2026-09-09", "amount_sen": 5},
        )

    assert err.value.code == UNIQUE_VIOLATION


def test_a_transaction_cannot_point_at_another_users_plan_or_item(db, two_users):
    a, b = (u["id"] for u in two_users)
    plan_of_b = make_plan(db, b, provider="spaylater")
    item_of_b = recurring_items.create(
        db, b, kind="bill", name="Rent", amount_sen=50000, cadence="monthly", anchor_date=PURCHASE
    )

    for link in ({"bnpl_plan_id": plan_of_b["id"]}, {"recurring_item_id": item_of_b["id"]}):
        with pytest.raises(APIError) as err:
            transactions.create(
                db,
                a,
                date=PURCHASE,
                amount_sen=100,
                type="expense",
                category="Food",
                **link,
            )
        assert err.value.code == FK_VIOLATION


def test_deleting_a_plan_or_item_unlinks_but_keeps_the_transactions(db, two_users):
    a = two_users[0]["id"]
    plan = make_plan(db, a, provider="atome")
    item = recurring_items.create(
        db, a, kind="bill", name="Rent", amount_sen=50000, cadence="monthly", anchor_date=PURCHASE
    )
    rent = transactions.create(
        db,
        a,
        date=PURCHASE,
        amount_sen=50000,
        type="expense",
        category="Rent",
        recurring_item_id=item["id"],
    )

    assert plans_repo.delete(db, a, plan["id"]) is True
    assert recurring_items.delete(db, a, item["id"]) is True

    kept_payment = db.table("transactions").select("*").eq("user_id", a).eq("category", "BNPL")
    (payment,) = kept_payment.execute().data
    assert payment["bnpl_plan_id"] is None and payment["user_id"] == a
    assert transactions.get(db, a, rent["id"])["recurring_item_id"] is None
    assert db.table("bnpl_installments").select("*").eq("plan_id", plan["id"]).execute().data == []


def test_marking_paid_twice_is_refused_and_logged_once(db, two_users):
    a = two_users[0]["id"]
    plan = make_plan(db, a, provider="spaylater")

    plans_repo.mark_paid(db, a, plan["id"], 1, date(2026, 4, 4))
    with pytest.raises(plans_repo.AlreadyPaidError):
        plans_repo.mark_paid(db, a, plan["id"], 1, date(2026, 4, 5))

    assert len(transactions.list_for_plan(db, a, plan["id"])) == 1


def test_the_conditional_flip_matches_nothing_once_paid(db, two_users):
    a = two_users[0]["id"]
    plan = make_plan(db, a, provider="spaylater")
    instalment = plan["installments"][0]
    table = ScopedTable(db, "bnpl_installments")

    first = table.update(a, instalment["id"], {"is_paid": True}, where={"is_paid": False})
    second = table.update(a, instalment["id"], {"is_paid": True}, where={"is_paid": False})

    assert first is not None and second is None


def test_provider_limit_upsert_is_atomic_and_per_user(db, two_users):
    a, b = (u["id"] for u in two_users)

    provider_limits.upsert_limit(db, a, "spaylater", 20000)
    provider_limits.upsert_limit(db, a, "spaylater", 30000)
    provider_limits.upsert_limit(db, b, "spaylater", 99999)

    assert provider_limits.get_limit(db, a, "spaylater") == 30000
    assert provider_limits.get_limit(db, b, "spaylater") == 99999
    assert len(provider_limits.list_limits(db, a)) == 1


def test_bulk_create_survives_more_rows_than_one_request_holds(db, two_users):
    a = two_users[0]["id"]
    rows = [
        {"date": date(2026, 3, 1), "amount_sen": n + 1, "type": "expense", "category": "Food"}
        for n in range(1203)
    ]

    created = transactions.bulk_create(db, a, rows, source="csv")

    assert created == 1203
    assert len(transactions.list_between(db, a, date(2026, 3, 1), date(2026, 3, 1))) == 1203
