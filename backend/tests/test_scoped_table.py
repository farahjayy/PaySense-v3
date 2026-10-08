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

    assert [r["amount_sen"] for r in table.list_rows(amir)] == [100]
    assert [r["amount_sen"] for r in table.list_rows(siti)] == [200]


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

    expenses = table.list_rows(amir, order_by="amount_sen", descending=True, type="expense")
    assert [r["amount_sen"] for r in expenses] == [200, 100]
    assert len(table.list_rows(amir, limit=1)) == 1


def test_list_refuses_a_user_id_filter(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")

    with pytest.raises(ValueError, match="user_id"):
        table.list_rows(amir, user_id=siti)


@pytest.mark.parametrize("bad", [None, "", "   "])
def test_every_operation_requires_a_user_id(db, bad):
    table = ScopedTable(db, "transactions")

    with pytest.raises(ValueError, match="user_id"):
        table.list_rows(bad)
    with pytest.raises(ValueError, match="user_id"):
        table.get(bad, "x")
    with pytest.raises(ValueError, match="user_id"):
        table.insert(bad, _txn())
    with pytest.raises(ValueError, match="user_id"):
        table.update(bad, "x", {"amount_sen": 1})
    with pytest.raises(ValueError, match="user_id"):
        table.delete(bad, "x")


def test_list_rows_returns_every_row_beyond_the_postgrest_cap(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")
    for n in range(1, 1501):
        db.rows("transactions").append(
            {"id": f"{n:08d}-0000-4000-8000-000000000000", "user_id": amir, **_txn(n)}
        )
    table.insert(siti, _txn(7))

    rows = table.list_rows(amir)

    assert len(rows) == 1500
    assert len({r["id"] for r in rows}) == 1500  # no duplicates across pages


def test_list_rows_orders_across_page_boundaries(db, two_users):
    amir, _ = two_users
    table = ScopedTable(db, "transactions")
    for n in range(1, 1201):
        db.rows("transactions").append(
            {"id": f"{n:08d}-0000-4000-8000-000000000000", "user_id": amir, **_txn(n)}
        )

    rows = table.list_rows(amir, order_by="amount_sen", descending=True)

    assert [r["amount_sen"] for r in rows] == list(range(1200, 0, -1))


def test_list_rows_limit_larger_than_a_page_is_honoured(db, two_users):
    amir, _ = two_users
    table = ScopedTable(db, "transactions")
    for n in range(1, 1501):
        db.rows("transactions").append(
            {"id": f"{n:08d}-0000-4000-8000-000000000000", "user_id": amir, **_txn(n)}
        )

    assert len(table.list_rows(amir, limit=1200)) == 1200
    assert len(table.list_rows(amir, limit=5)) == 5


@pytest.mark.parametrize("bad_id", ["abc", "", "1; drop table x", "../../etc"])
def test_a_malformed_row_id_is_simply_not_found(db, two_users, bad_id):
    amir, _ = two_users
    table = ScopedTable(db, "transactions")

    assert table.get(amir, bad_id) is None
    assert table.update(amir, bad_id, {"amount_sen": 1}) is None
    assert table.delete(amir, bad_id) is False


def test_list_rows_refuses_a_none_filter(db, two_users):
    amir, _ = two_users

    with pytest.raises(ValueError, match="None"):
        ScopedTable(db, "transactions").list_rows(amir, category=None)


# ------------------------------------------------------------------ range filters and batches
def _dated(day: str, amount: int = 100) -> dict:
    return _txn(amount, date=day)


def test_between_filters_inclusively_and_either_end_may_be_open(db, two_users):
    amir, _ = two_users
    table = ScopedTable(db, "transactions")
    for day in ("2026-01-05", "2026-01-10", "2026-01-15", "2026-01-20", "2026-01-25"):
        table.insert(amir, _dated(day))

    both = table.list_rows(amir, between={"date": ("2026-01-10", "2026-01-20")}, order_by="date")
    from_only = table.list_rows(amir, between={"date": ("2026-01-20", None)}, order_by="date")
    to_only = table.list_rows(amir, between={"date": (None, "2026-01-10")}, order_by="date")

    assert [r["date"] for r in both] == ["2026-01-10", "2026-01-15", "2026-01-20"]
    assert [r["date"] for r in from_only] == ["2026-01-20", "2026-01-25"]
    assert [r["date"] for r in to_only] == ["2026-01-05", "2026-01-10"]


def test_between_accepts_date_objects(db, two_users):
    from datetime import date

    amir, _ = two_users
    table = ScopedTable(db, "transactions")
    table.insert(amir, _dated("2026-01-10"))

    rows = table.list_rows(amir, between={"date": (date(2026, 1, 10), date(2026, 1, 10))})

    assert len(rows) == 1


def test_between_never_leaks_another_users_rows(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")
    table.insert(siti, _dated("2026-01-10"))

    assert table.list_rows(amir, between={"date": ("2026-01-01", "2026-12-31")}) == []


def test_insert_many_stamps_every_row_and_returns_them_in_order(db, two_users):
    amir, _ = two_users
    table = ScopedTable(db, "transactions")

    created = table.insert_many(amir, [_txn(100), _txn(200), _txn(300)])

    assert [r["amount_sen"] for r in created] == [100, 200, 300]
    assert {r["user_id"] for r in created} == {amir}


def test_insert_many_rejects_a_row_for_another_user_before_writing_anything(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")

    with pytest.raises(ValueError, match="user_id"):
        table.insert_many(amir, [_txn(100), _txn(200, user_id=siti)])

    assert db.rows("transactions") == []


def test_insert_many_of_nothing_is_a_no_op(db, two_users):
    amir, _ = two_users

    assert ScopedTable(db, "transactions").insert_many(amir, []) == []


def test_delete_many_only_removes_the_callers_rows_and_ignores_junk_ids(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")
    mine = [table.insert(amir, _txn(n))["id"] for n in (1, 2, 3)]
    theirs = table.insert(siti, _txn(9))["id"]

    removed = table.delete_many(amir, [mine[0], mine[1], theirs, "not-a-uuid"])

    assert removed == 2
    assert table.get(siti, theirs) is not None
    assert [r["id"] for r in table.list_rows(amir)] == [mine[2]]


def test_delete_many_of_nothing_removes_nothing(db, two_users):
    amir, _ = two_users

    assert ScopedTable(db, "transactions").delete_many(amir, []) == 0


def test_update_where_only_applies_when_the_row_still_matches(db, two_users):
    amir, _ = two_users
    table = ScopedTable(db, "transactions")
    row = table.insert(amir, _txn(500, is_bnpl=False))

    first = table.update(amir, row["id"], {"amount_sen": 1}, where={"is_bnpl": False})
    second = table.update(amir, row["id"], {"amount_sen": 2}, where={"is_bnpl": True})

    assert first["amount_sen"] == 1
    assert second is None
    assert table.get(amir, row["id"])["amount_sen"] == 1


def test_update_where_cannot_name_the_owner_column(db, two_users):
    amir, siti = two_users
    table = ScopedTable(db, "transactions")
    row = table.insert(siti, _txn())

    with pytest.raises(ValueError, match="user_id"):
        table.update(amir, row["id"], {"amount_sen": 1}, where={"user_id": siti})
