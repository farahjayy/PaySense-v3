from datetime import date

import pytest

from app.db import recurring_items as repo
from app.db import transactions
from app.db.users import create as create_user
from tests.fakes import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def amir(db) -> str:
    return create_user(db, username="amir", display_name="Amir")["id"]


@pytest.fixture
def siti(db) -> str:
    return create_user(db, username="siti", display_name="Siti")["id"]


def make(db, user_id, **overrides):
    values = {
        "kind": "income",
        "name": "Monthly allowance",
        "amount_sen": 80000,
        "cadence": "monthly",
        "anchor_date": date(2026, 1, 1),
    }
    return repo.create(db, user_id, **{**values, **overrides})


def test_create_is_a_manual_active_item(db, amir):
    item = make(db, amir)

    assert item["origin"] == "manual"
    assert item["active"] is True
    assert item["anchor_date"] == "2026-01-01"
    assert item["custom_interval_days"] is None
    assert item["name"] == "Monthly allowance"


def test_custom_cadence_needs_an_interval_in_days(db, amir):
    item = make(db, amir, cadence="custom", custom_interval_days=10)

    assert item["custom_interval_days"] == 10
    with pytest.raises(ValueError, match="interval"):
        make(db, amir, cadence="custom")
    with pytest.raises(ValueError, match="interval"):
        make(db, amir, cadence="custom", custom_interval_days=0)


def test_a_fixed_cadence_ignores_a_stray_interval(db, amir):
    assert make(db, amir, cadence="weekly", custom_interval_days=9)["custom_interval_days"] is None


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"kind": "gift"}, "kind"),
        ({"name": "  "}, "name"),
        ({"amount_sen": 0}, "amount"),
        ({"amount_sen": 1.5}, "amount"),
        ({"cadence": "daily"}, "cadence"),
    ],
)
def test_create_validates(db, amir, overrides, message):
    with pytest.raises(ValueError, match=message):
        make(db, amir, **overrides)

    assert db.rows("recurring_items") == []


def test_list_items_can_filter_to_the_active_ones(db, amir):
    keep = make(db, amir, name="Rent", kind="bill")
    paused = make(db, amir, name="Gym", kind="bill")
    repo.update(db, amir, paused["id"], {"active": False})

    everything = repo.list_items(db, amir)
    active = repo.list_items(db, amir, active_only=True)

    assert {i["id"] for i in everything} == {keep["id"], paused["id"]}
    assert [i["id"] for i in active] == [keep["id"]]


def test_update_merges_with_the_stored_row_before_validating(db, amir):
    item = make(db, amir, cadence="custom", custom_interval_days=10)

    updated = repo.update(db, amir, item["id"], {"cadence": "weekly"})

    assert updated["cadence"] == "weekly"
    assert updated["custom_interval_days"] is None  # no longer meaningful

    with pytest.raises(ValueError, match="interval"):
        repo.update(db, amir, item["id"], {"cadence": "custom"})


@pytest.mark.parametrize(
    "patch", [{"user_id": "x"}, {"id": "x"}, {"origin": "detected"}, {"kind": "bill"}, {"nope": 1}]
)
def test_update_refuses_fields_it_does_not_own(db, amir, patch):
    item = make(db, amir)

    with pytest.raises(ValueError, match="cannot be updated"):
        repo.update(db, amir, item["id"], patch)


def test_update_of_a_missing_item_is_none(db, amir):
    assert repo.update(db, amir, "00000000-0000-4000-8000-000000000000", {"active": False}) is None


def test_deleting_an_item_unlinks_but_keeps_its_transactions(db, amir):
    item = make(db, amir)
    txn = transactions.create(
        db,
        amir,
        date=date(2026, 2, 1),
        amount_sen=80000,
        type="income",
        category="Allowance",
        recurring_item_id=item["id"],
    )

    assert repo.delete(db, amir, item["id"]) is True

    kept = transactions.get(db, amir, txn["id"])
    assert kept is not None
    assert kept["recurring_item_id"] is None


# ------------------------------------------------------------------ isolation (one per function)
def test_isolation_get(db, amir, siti):
    item = make(db, amir)

    assert repo.get(db, siti, item["id"]) is None


def test_isolation_list_items(db, amir, siti):
    make(db, amir)

    assert repo.list_items(db, siti) == []


def test_isolation_update(db, amir, siti):
    item = make(db, amir)

    assert repo.update(db, siti, item["id"], {"name": "Hijacked"}) is None
    assert repo.get(db, amir, item["id"])["name"] == "Monthly allowance"


def test_isolation_delete(db, amir, siti):
    item = make(db, amir)

    assert repo.delete(db, siti, item["id"]) is False
    assert repo.get(db, amir, item["id"]) is not None


def test_a_transaction_cannot_be_linked_to_another_users_item(db, amir, siti):
    from postgrest import APIError

    item = make(db, amir)

    with pytest.raises(APIError):
        transactions.create(
            db,
            siti,
            date=date(2026, 2, 1),
            amount_sen=100,
            type="income",
            category="Allowance",
            recurring_item_id=item["id"],
        )
