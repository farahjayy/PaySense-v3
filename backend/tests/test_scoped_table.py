import pytest

from app.db.base import ScopedTable
from app.db.users import create as create_user
from tests.fakes import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def two_users(db):
    amir = create_user(db, username="amir", display_name="Amir")
    siti = create_user(db, username="siti", display_name="Siti")
    return amir["id"], siti["id"]


def _txn(amount_sen: int = 1000, **extra) -> dict:
    return {
        "date": "2026-01-05",
        "amount_sen": amount_sen,
        "type": "expense",
        "category": "Food",
        **extra,
    }


def test_insert_stamps_the_user_id(db, two_users):
    amir, _ = two_users
    table = ScopedTable(db, "transactions")

    row = table.insert(amir, _txn())

    assert row["user_id"] == amir


def test_insert_rejects_a_row_for_a_different_user(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")

    with pytest.raises(ValueError, match="user_id"):
        table.insert(amir, _txn(user_id=siti))


def test_list_returns_only_the_callers_rows(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")
    table.insert(amir, _txn(100))
    table.insert(siti, _txn(200))

    assert [r["amount_sen"] for r in table.list(amir)] == [100]
    assert [r["amount_sen"] for r in table.list(siti)] == [200]


def test_get_cannot_read_another_users_row(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")
    row = table.insert(siti, _txn())

    assert table.get(amir, row["id"]) is None
    assert table.get(siti, row["id"]) is not None


def test_update_cannot_touch_another_users_row(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")
    row = table.insert(siti, _txn(500))

    assert table.update(amir, row["id"], {"amount_sen": 1}) is None
    assert table.get(siti, row["id"])["amount_sen"] == 500


def test_update_refuses_to_change_ownership(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")
    row = table.insert(amir, _txn())

    with pytest.raises(ValueError, match="user_id"):
        table.update(amir, row["id"], {"user_id": siti})


def test_delete_cannot_remove_another_users_row(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")
    row = table.insert(siti, _txn())

    assert table.delete(amir, row["id"]) is False
    assert table.get(siti, row["id"]) is not None
    assert table.delete(siti, row["id"]) is True


def test_list_supports_filters_order_and_limit(db, two_users):
    amir, _ = two_users
    table = ScopedTable(db, "transactions")
    for amount in (300, 100, 200):
        table.insert(amir, _txn(amount, type="income" if amount == 300 else "expense"))

    expenses = table.list(amir, order_by="amount_sen", descending=True, type="expense")
    assert [r["amount_sen"] for r in expenses] == [200, 100]
    assert len(table.list(amir, limit=1)) == 1


def test_list_refuses_a_user_id_filter(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")

    with pytest.raises(ValueError, match="user_id"):
        table.list(amir, user_id=siti)


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_every_operation_requires_a_user_id(db, bad):
    table = ScopedTable(db, "transactions")

    with pytest.raises(ValueError, match="user_id"):
        table.list(bad)
    with pytest.raises(ValueError, match="user_id"):
        table.get(bad, "x")
    with pytest.raises(ValueError, match="user_id"):
        table.insert(bad, _txn())
    with pytest.raises(ValueError, match="user_id"):
        table.update(bad, "x", {"amount_sen": 1})
    with pytest.raises(ValueError, match="user_id"):
        table.delete(bad, "x")
