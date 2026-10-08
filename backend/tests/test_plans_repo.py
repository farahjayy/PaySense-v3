from datetime import date

import pytest

from app.db import plans as repo
from app.db import transactions
from app.db.users import create as create_user
from app.domain.providers import get_provider
from app.domain.schedule import build_manual_schedule, build_schedule
from tests.fakes import FakeSupabase

PURCHASE = date(2026, 3, 5)


@pytest.fixture
def db() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def amir(db) -> str:
    return create_user(db, username="amir", display_name="Amir")["id"]


@pytest.fixture
def siti(db) -> str:
    return create_user(db, username="siti", display_name="Siti")["id"]


def plan_input(provider="atome", item="Phone", price=30000, count=3, upfront=0):
    """A plan dict + its instalments, as the API layer would build them with the domain code."""
    financed = price - upfront
    config = get_provider(provider)
    if config.rule_driven:
        instalments = build_schedule(provider, financed, 0, count, PURCHASE)
        source = "provider_rule"
    else:
        instalments = build_manual_schedule(PURCHASE, count, total_payable_sen=financed)
        source = "manual"
    plan = {
        "item_name": item,
        "provider": provider,
        "provider_label": config.label,
        "schedule_source": source,
        "total_price_sen": price,
        "financed_sen": financed,
        "upfront_sen": upfront,
        "monthly_fee_rate_pct": 0,
        "num_installments": count,
        "purchase_date": PURCHASE,
        "first_payment_date": instalments[0].due_date,
    }
    return plan, instalments


def create(db, user_id, **kwargs):
    plan, instalments = plan_input(**kwargs)
    return repo.create_plan(db, user_id, plan, instalments)


# ------------------------------------------------------------------ create
def test_create_stores_the_plan_and_its_instalments_in_order(db, amir):
    created = create(db, amir, provider="spaylater", price=30000, count=3)

    assert created["user_id"] == amir
    assert created["item_name"] == "Phone"
    assert created["total_price_sen"] == 30000
    assert [i["seq"] for i in created["installments"]] == [1, 2, 3]
    assert [i["amount_sen"] for i in created["installments"]] == [10000, 10000, 10000]
    assert [i["due_date"] for i in created["installments"]] == [
        "2026-04-05",
        "2026-05-05",
        "2026-06-05",
    ]
    assert not any(i["is_paid"] for i in created["installments"])
    assert db.rows("transactions") == []  # nothing is paid at checkout with SPayLater


def test_an_atome_checkout_instalment_is_paid_and_logged(db, amir):
    created = create(db, amir, provider="atome", price=30000, count=3)

    first, second, _ = created["installments"]
    assert first["is_paid"] is True and first["paid_date"] == "2026-03-05"
    assert second["is_paid"] is False
    (logged,) = transactions.list_for_plan(db, amir, created["id"])
    assert logged["amount_sen"] == 10000
    assert (
        logged["type"] == "expense" and logged["category"] == "BNPL" and logged["is_bnpl"] is True
    )
    assert logged["date"] == "2026-03-05"
    assert logged["description"] == "Atome instalment 1/3 — Phone"


def test_the_excess_over_the_limit_is_logged_as_a_checkout_payment(db, amir):
    # D-28: price RM300, limit leaves RM200 financeable -> RM100 paid at checkout.
    created = create(db, amir, provider="spaylater", price=30000, count=2, upfront=10000)

    assert (created["financed_sen"], created["upfront_sen"]) == (20000, 10000)
    (logged,) = transactions.list_for_plan(db, amir, created["id"])
    assert logged["amount_sen"] == 10000
    assert logged["description"] == "SPayLater checkout payment — Phone"
    assert logged["date"] == "2026-03-05"


def test_atome_with_an_excess_logs_both_checkout_amounts(db, amir):
    created = create(db, amir, provider="atome", price=30000, count=3, upfront=3000)

    logged = transactions.list_for_plan(db, amir, created["id"])
    assert sorted(t["amount_sen"] for t in logged) == [3000, 9000]


def test_a_manual_other_plan_logs_nothing_at_checkout(db, amir):
    created = create(db, amir, provider="other", price=10001, count=3)

    assert created["schedule_source"] == "manual"
    assert [i["amount_sen"] for i in created["installments"]] == [3333, 3333, 3335]
    assert db.rows("transactions") == []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"provider": "grab_paylater"}, "provider"),
        ({"item_name": "  "}, "item_name"),
        ({"provider_label": ""}, "provider_label"),
        ({"schedule_source": "magic"}, "schedule_source"),
        ({"financed_sen": 1}, "financed"),  # financed + upfront must equal the price
        ({"financed_sen": 0, "upfront_sen": 30000}, "financed"),
        ({"upfront_sen": -1, "financed_sen": 30001}, "upfront"),
        ({"num_installments": 4}, "instalments"),
        ({"first_payment_date": date(2030, 1, 1)}, "first_payment_date"),
    ],
)
def test_create_rejects_inconsistent_plans_before_writing(db, amir, change, message):
    plan, instalments = plan_input()
    plan.update(change)

    with pytest.raises(ValueError, match=message):
        repo.create_plan(db, amir, plan, instalments)

    assert db.rows("bnpl_plans") == [] and db.rows("bnpl_installments") == []


def test_create_rejects_instalments_that_do_not_run_from_one(db, amir):
    plan, instalments = plan_input()

    with pytest.raises(ValueError, match="seq"):
        repo.create_plan(db, amir, plan, [instalments[0], instalments[2], instalments[1]])


def test_a_failure_writing_instalments_leaves_no_plan_behind(db, amir, monkeypatch):
    real = repo.ScopedTable.insert_many

    def fail_on_instalments(self, user_id, rows):
        if self._table == "bnpl_installments":
            raise RuntimeError("database went away")
        return real(self, user_id, rows)

    monkeypatch.setattr(repo.ScopedTable, "insert_many", fail_on_instalments)
    plan, instalments = plan_input()

    with pytest.raises(RuntimeError, match="went away"):
        repo.create_plan(db, amir, plan, instalments)

    assert db.rows("bnpl_plans") == []
    assert db.rows("bnpl_installments") == []


def test_a_failure_logging_checkout_payments_removes_everything(db, amir, monkeypatch):
    real = repo.ScopedTable.insert

    def fail_on_second_transaction(self, user_id, row):
        if self._table == "transactions" and len(db.rows("transactions")) >= 1:
            raise RuntimeError("database went away")
        return real(self, user_id, row)

    monkeypatch.setattr(repo.ScopedTable, "insert", fail_on_second_transaction)
    plan, instalments = plan_input(provider="atome", upfront=3000)  # two checkout payments

    with pytest.raises(RuntimeError, match="went away"):
        repo.create_plan(db, amir, plan, instalments)

    assert db.rows("bnpl_plans") == []
    assert db.rows("bnpl_installments") == []
    assert db.rows("transactions") == []  # the first logged payment was removed too


# ------------------------------------------------------------------ read
def test_list_with_instalments_returns_newest_plan_first_with_ordered_instalments(db, amir):
    older = create(db, amir, item="Earbuds", provider="spaylater")
    db.rows("bnpl_plans")[0]["created_at"] = "2026-01-01T00:00:00+00:00"
    newer = create(db, amir, item="Laptop", provider="tiktok_paylater")

    listed = repo.list_with_instalments(db, amir)

    assert [p["id"] for p in listed] == [newer["id"], older["id"]]
    assert all([i["seq"] for i in p["installments"]] == [1, 2, 3] for p in listed)


def test_get_with_instalments_of_a_missing_or_malformed_id_is_none(db, amir):
    assert repo.get_with_instalments(db, amir, "00000000-0000-4000-8000-000000000000") is None
    assert repo.get_with_instalments(db, amir, "not-a-uuid") is None


def test_used_limits_sum_the_unpaid_instalments_per_provider(db, amir):
    create(db, amir, provider="spaylater", price=30000, count=3)
    atome = create(db, amir, provider="atome", price=30000, count=3)  # first one paid at checkout
    assert atome["installments"][0]["is_paid"]

    used = repo.used_limits(db, amir)

    assert used == {"spaylater": 30000, "atome": 20000}


# ------------------------------------------------------------------ rename
def test_rename_updates_the_plan_and_the_descriptions_it_wrote(db, amir):
    created = create(db, amir, provider="atome")  # logs "Atome instalment 1/3 — Phone"
    transactions.create(
        db,
        amir,
        date=PURCHASE,
        amount_sen=500,
        type="expense",
        category="BNPL",
        description="Atome fee — my own words",
        bnpl_plan_id=created["id"],
    )

    renamed = repo.rename(db, amir, created["id"], "Phone Case")

    assert renamed["item_name"] == "Phone Case"
    descriptions = sorted(
        t["description"] for t in transactions.list_for_plan(db, amir, created["id"])
    )
    assert descriptions == ["Atome fee — my own words", "Atome instalment 1/3 — Phone Case"]


@pytest.mark.parametrize("bad", ["", "   ", "x" * 121])
def test_rename_validates_the_name(db, amir, bad):
    created = create(db, amir)

    with pytest.raises(ValueError, match="item_name"):
        repo.rename(db, amir, created["id"], bad)


# ------------------------------------------------------------------ delete
def test_delete_keeps_logged_payments_by_default_and_unlinks_them(db, amir):
    created = create(db, amir, provider="atome")

    assert repo.delete(db, amir, created["id"]) is True

    assert repo.get_with_instalments(db, amir, created["id"]) is None
    assert db.rows("bnpl_installments") == []
    (kept,) = db.rows("transactions")
    assert kept["bnpl_plan_id"] is None


def test_delete_can_remove_the_logged_payments_too(db, amir):
    created = create(db, amir, provider="atome")

    assert repo.delete(db, amir, created["id"], keep_payments=False) is True

    assert db.rows("transactions") == []


# ------------------------------------------------------------------ mark paid
def test_mark_paid_logs_the_payment_then_flips_the_instalment(db, amir):
    created = create(db, amir, provider="spaylater")

    paid = repo.mark_paid(db, amir, created["id"], 1, date(2026, 4, 4))

    assert paid["is_paid"] is True and paid["paid_date"] == "2026-04-04"
    (logged,) = transactions.list_for_plan(db, amir, created["id"])
    assert logged["amount_sen"] == 10000
    assert logged["date"] == "2026-04-04"
    assert logged["description"] == "SPayLater instalment 1/3 — Phone"


def test_marking_the_same_instalment_twice_is_refused_and_not_double_logged(db, amir):
    created = create(db, amir, provider="spaylater")
    repo.mark_paid(db, amir, created["id"], 1, date(2026, 4, 4))

    with pytest.raises(repo.AlreadyPaidError):
        repo.mark_paid(db, amir, created["id"], 1, date(2026, 4, 5))

    assert len(transactions.list_for_plan(db, amir, created["id"])) == 1


def test_mark_paid_of_an_unknown_plan_or_seq_is_none(db, amir):
    created = create(db, amir, provider="spaylater")

    assert repo.mark_paid(db, amir, "00000000-0000-4000-8000-000000000000", 1, PURCHASE) is None
    assert repo.mark_paid(db, amir, created["id"], 9, PURCHASE) is None
    assert db.rows("transactions") == []


def test_if_the_flip_loses_a_race_the_logged_payment_is_removed(db, amir, monkeypatch):
    created = create(db, amir, provider="spaylater")
    monkeypatch.setattr(repo.ScopedTable, "update", lambda self, *a, **k: None)  # someone else won

    with pytest.raises(repo.PlanConflictError):
        repo.mark_paid(db, amir, created["id"], 1, date(2026, 4, 4))

    assert db.rows("transactions") == []  # no orphan payment


def test_if_the_flip_errors_the_logged_payment_is_removed(db, amir, monkeypatch):
    created = create(db, amir, provider="spaylater")

    def boom(self, *args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(repo.ScopedTable, "update", boom)

    with pytest.raises(RuntimeError, match="went away"):
        repo.mark_paid(db, amir, created["id"], 1, date(2026, 4, 4))

    assert db.rows("transactions") == []


def test_mark_paid_many_pays_each_in_order(db, amir):
    created = create(db, amir, provider="spaylater")

    paid = repo.mark_paid_many(db, amir, created["id"], [2, 1], date(2026, 6, 6))

    assert [p["seq"] for p in paid] == [1, 2]
    assert len(transactions.list_for_plan(db, amir, created["id"])) == 2


def test_mark_paid_many_checks_everything_before_paying_anything(db, amir):
    created = create(db, amir, provider="spaylater")
    repo.mark_paid(db, amir, created["id"], 1, date(2026, 4, 4))

    with pytest.raises(repo.AlreadyPaidError):
        repo.mark_paid_many(db, amir, created["id"], [2, 1], date(2026, 6, 6))
    with pytest.raises(ValueError, match="seq"):
        repo.mark_paid_many(db, amir, created["id"], [2, 9], date(2026, 6, 6))

    assert len(transactions.list_for_plan(db, amir, created["id"])) == 1  # nothing extra was paid


# ------------------------------------------------------------------ isolation (one per function)
def test_isolation_create_plan_stamps_the_caller_only(db, amir, siti):
    created = create(db, siti)

    assert created["user_id"] == siti
    assert repo.list_with_instalments(db, amir) == []
    assert {i["user_id"] for i in db.rows("bnpl_installments")} == {siti}


def test_isolation_get_with_instalments(db, amir, siti):
    created = create(db, amir)

    assert repo.get_with_instalments(db, siti, created["id"]) is None


def test_isolation_list_with_instalments(db, amir, siti):
    create(db, amir)

    assert repo.list_with_instalments(db, siti) == []


def test_isolation_used_limits(db, amir, siti):
    create(db, amir, provider="spaylater")

    assert repo.used_limits(db, siti) == {}


def test_isolation_rename(db, amir, siti):
    created = create(db, amir)

    assert repo.rename(db, siti, created["id"], "Hijacked") is None
    assert repo.get_with_instalments(db, amir, created["id"])["item_name"] == "Phone"


def test_isolation_delete(db, amir, siti):
    created = create(db, amir, provider="atome")

    assert repo.delete(db, siti, created["id"], keep_payments=False) is False
    assert repo.get_with_instalments(db, amir, created["id"]) is not None
    assert len(db.rows("transactions")) == 1  # the other user's payments were not touched


def test_isolation_mark_paid(db, amir, siti):
    created = create(db, amir, provider="spaylater")

    assert repo.mark_paid(db, siti, created["id"], 1, PURCHASE) is None
    assert db.rows("transactions") == []
    assert not repo.get_with_instalments(db, amir, created["id"])["installments"][0]["is_paid"]


def test_isolation_mark_paid_many(db, amir, siti):
    created = create(db, amir, provider="spaylater")

    assert repo.mark_paid_many(db, siti, created["id"], [1], PURCHASE) == []
    assert db.rows("transactions") == []
