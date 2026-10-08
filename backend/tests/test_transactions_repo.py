from datetime import date

import pytest

from app.db import transactions as repo
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


def make(db, user_id, day="2026-03-05", amount_sen=1000, **extra):
    return repo.create(
        db,
        user_id,
        date=date.fromisoformat(day),
        amount_sen=amount_sen,
        type=extra.pop("type", "expense"),
        category=extra.pop("category", "Food"),
        **extra,
    )


# ------------------------------------------------------------------ behaviour
def test_create_returns_the_stored_row_with_defaults(db, amir):
    row = make(db, amir, description="Nasi lemak")

    assert row["user_id"] == amir
    assert row["amount_sen"] == 1000
    assert row["date"] == "2026-03-05"
    assert row["is_bnpl"] is False
    assert row["source"] == "manual"
    assert row["description"] == "Nasi lemak"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"amount_sen": 0}, "amount"),
        ({"amount_sen": -5}, "amount"),
        ({"amount_sen": 12.5}, "amount"),
        ({"amount_sen": True}, "amount"),
        ({"type": "gift"}, "type"),
        ({"category": "   "}, "category"),
        ({"source": "pdf"}, "source"),
    ],
)
def test_create_validates_before_touching_the_database(db, amir, overrides, message):
    with pytest.raises(ValueError, match=message):
        make(db, amir, **overrides)

    assert db.rows("transactions") == []


def test_list_between_is_inclusive_newest_first_and_filters(db, amir):
    make(db, amir, "2026-03-01", 100)
    make(db, amir, "2026-03-10", 200, type="income", category="Salary")
    make(db, amir, "2026-03-20", 300)
    make(db, amir, "2026-04-02", 400)

    rows = repo.list_between(db, amir, date(2026, 3, 1), date(2026, 3, 20))
    expenses = repo.list_between(db, amir, date(2026, 3, 1), date(2026, 3, 31), type="expense")
    salary = repo.list_between(db, amir, date(2026, 3, 1), date(2026, 3, 31), category="Salary")

    assert [r["amount_sen"] for r in rows] == [300, 200, 100]
    assert [r["amount_sen"] for r in expenses] == [300, 100]
    assert [r["amount_sen"] for r in salary] == [200]


def test_list_between_can_be_oldest_first(db, amir):
    make(db, amir, "2026-03-01", 100)
    make(db, amir, "2026-03-02", 200)

    rows = repo.list_between(db, amir, date(2026, 3, 1), date(2026, 3, 2), newest_first=False)

    assert [r["amount_sen"] for r in rows] == [100, 200]


def test_update_changes_only_allowed_fields(db, amir):
    row = make(db, amir)

    updated = repo.update(db, amir, row["id"], {"amount_sen": 2500, "category": "Transport"})

    assert (updated["amount_sen"], updated["category"]) == (2500, "Transport")
    assert repo.get(db, amir, row["id"])["amount_sen"] == 2500


@pytest.mark.parametrize(
    "patch",
    [{"user_id": "x"}, {"id": "x"}, {"bnpl_plan_id": "x"}, {"source": "csv"}, {"unknown": 1}],
)
def test_update_refuses_fields_it_does_not_own(db, amir, patch):
    row = make(db, amir)

    with pytest.raises(ValueError, match="cannot be updated"):
        repo.update(db, amir, row["id"], patch)


def test_update_validates_values(db, amir):
    row = make(db, amir)

    with pytest.raises(ValueError, match="amount"):
        repo.update(db, amir, row["id"], {"amount_sen": 0})


def test_delete(db, amir):
    row = make(db, amir)

    assert repo.delete(db, amir, row["id"]) is True
    assert repo.get(db, amir, row["id"]) is None
    assert repo.delete(db, amir, row["id"]) is False


def test_bulk_create_inserts_in_chunks_and_counts(db, amir):
    rows = [
        {"date": date(2026, 3, 1), "amount_sen": n + 1, "type": "expense", "category": "Food"}
        for n in range(1203)
    ]

    created = repo.bulk_create(db, amir, rows, source="csv")

    assert created == 1203
    stored = db.rows("transactions")
    assert len(stored) == 1203
    assert {r["source"] for r in stored} == {"csv"}
    assert {r["user_id"] for r in stored} == {amir}


def test_bulk_create_validates_every_row_before_writing(db, amir):
    rows = [
        {"date": date(2026, 3, 1), "amount_sen": 100, "type": "expense", "category": "Food"},
        {"date": date(2026, 3, 1), "amount_sen": 0, "type": "expense", "category": "Food"},
    ]

    with pytest.raises(ValueError, match="amount"):
        repo.bulk_create(db, amir, rows, source="csv")

    assert db.rows("transactions") == []


def test_bulk_create_removes_what_it_wrote_if_a_later_chunk_fails(db, amir, monkeypatch):
    rows = [
        {"date": date(2026, 3, 1), "amount_sen": n + 1, "type": "expense", "category": "Food"}
        for n in range(repo.CHUNK_SIZE + 10)
    ]
    real_insert_many = repo.ScopedTable.insert_many
    calls = {"n": 0}

    def flaky(self, user_id, chunk):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("database went away")
        return real_insert_many(self, user_id, chunk)

    monkeypatch.setattr(repo.ScopedTable, "insert_many", flaky)

    with pytest.raises(RuntimeError, match="went away"):
        repo.bulk_create(db, amir, rows, source="csv")

    assert db.rows("transactions") == []  # the first chunk was rolled back


def test_fingerprints_between_match_the_import_parser(db, amir):
    from app.domain.csv_import import fingerprint

    make(db, amir, "2026-03-05", 1250, description="Mamak  dinner")
    make(db, amir, "2026-05-05", 999)

    prints = repo.fingerprints_between(db, amir, date(2026, 3, 1), date(2026, 3, 31))

    assert prints == [fingerprint(date(2026, 3, 5), 1250, "expense", "Mamak dinner")]


def test_list_and_delete_for_plan(db, amir):
    db.rows("transactions").append(
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "user_id": amir,
            "date": "2026-03-05",
            "amount_sen": 100,
            "type": "expense",
            "category": "BNPL",
            "bnpl_plan_id": "22222222-2222-4222-8222-222222222222",
        }
    )
    make(db, amir)

    linked = repo.list_for_plan(db, amir, "22222222-2222-4222-8222-222222222222")
    removed = repo.delete_for_plan(db, amir, "22222222-2222-4222-8222-222222222222")

    assert len(linked) == 1
    assert removed == 1
    assert len(db.rows("transactions")) == 1


# ------------------------------------------------------------------ isolation (one per function)
def test_isolation_get(db, amir, siti):
    row = make(db, amir)

    assert repo.get(db, siti, row["id"]) is None


def test_isolation_list_between(db, amir, siti):
    make(db, amir)

    assert repo.list_between(db, siti, date(2026, 1, 1), date(2026, 12, 31)) == []


def test_isolation_update(db, amir, siti):
    row = make(db, amir)

    assert repo.update(db, siti, row["id"], {"amount_sen": 1}) is None
    assert repo.get(db, amir, row["id"])["amount_sen"] == 1000


def test_isolation_delete(db, amir, siti):
    row = make(db, amir)

    assert repo.delete(db, siti, row["id"]) is False
    assert repo.get(db, amir, row["id"]) is not None


def test_isolation_bulk_create_stamps_the_caller(db, amir, siti):
    rows = [{"date": date(2026, 3, 1), "amount_sen": 5, "type": "expense", "category": "Food"}]

    repo.bulk_create(db, siti, rows, source="csv")

    assert repo.list_between(db, amir, date(2026, 1, 1), date(2026, 12, 31)) == []
    assert len(repo.list_between(db, siti, date(2026, 1, 1), date(2026, 12, 31))) == 1


def test_isolation_fingerprints_between(db, amir, siti):
    make(db, amir, "2026-03-05")

    assert repo.fingerprints_between(db, siti, date(2026, 3, 1), date(2026, 3, 31)) == []


def test_isolation_for_plan_functions(db, amir, siti):
    plan_id = "22222222-2222-4222-8222-222222222222"
    db.rows("transactions").append(
        {
            "id": "11111111-1111-4111-8111-111111111111",
            "user_id": amir,
            "date": "2026-03-05",
            "amount_sen": 100,
            "type": "expense",
            "category": "BNPL",
            "bnpl_plan_id": plan_id,
        }
    )

    assert repo.list_for_plan(db, siti, plan_id) == []
    assert repo.delete_for_plan(db, siti, plan_id) == 0
    assert len(db.rows("transactions")) == 1


def test_summary_rows_carry_only_the_columns_the_summary_needs(db, amir):
    make(db, amir, description="private note", account_name="Maybank")

    (row,) = repo.list_for_summary(db, amir)

    assert set(row) == {"date", "amount_sen", "type", "category"}


def test_isolation_list_for_summary(db, amir, siti):
    make(db, amir)

    assert repo.list_for_summary(db, siti) == []


def test_isolation_list_for_forecast(db, amir, siti):
    make(db, amir)

    assert repo.list_for_forecast(db, siti, date(2026, 6, 30)) == []


def test_forecast_rows_stop_at_today_and_cover_two_years(db, amir):
    make(db, amir, day="2026-06-01")
    make(db, amir, day="2026-07-15")  # after "today"
    make(db, amir, day="2024-05-31")  # more than 24 months before June 2026
    make(db, amir, day="2024-06-01")

    rows = repo.list_for_forecast(db, amir, date(2026, 6, 30))

    assert sorted(r["date"] for r in rows) == ["2024-06-01", "2026-06-01"]
    assert {"description", "recurring_item_id", "bnpl_plan_id", "is_bnpl"} <= set(rows[0])
