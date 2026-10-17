"""The competition migrations (0003 login hardening, 0004 budgets and assistant) against the REAL
Supabase project: `uv run pytest -m integration`. Each test skips, naming the migration, until the
author has applied it in the SQL editor (questions.md)."""

import pytest
from postgrest import APIError

from app.db import budgets, locks, users
from app.db.base import ScopedTable

pytestmark = pytest.mark.integration


def _needs(db, table: str, column: str, migration: str) -> None:
    try:
        db.table(table).select(column).limit(1).execute()
    except APIError:
        pytest.skip(f"apply migration {migration} first")


def test_0003_passphrase_and_token_version(db, two_users):
    _needs(db, "users", "passphrase_hash,token_version", "0003")
    amir = two_users[0]
    users.set_passphrase(db, amir["id"], "a long enough passphrase")
    row = users.get_by_id(db, amir["id"])
    assert row["passphrase_hash"].startswith("scrypt$")
    assert row["token_version"] == 1
    assert users.bump_token_version(db, amir["id"]) == 2


def test_0003_user_locks_are_atomic_and_per_user(db, two_users):
    _needs(db, "user_locks", "user_id", "0003")
    amir, siti = (u["id"] for u in two_users)
    assert locks.acquire(db, amir, "plan_create")
    assert not locks.acquire(db, amir, "plan_create")
    assert locks.acquire(db, siti, "plan_create")
    locks.release(db, amir, "plan_create")
    assert locks.acquire(db, amir, "plan_create")


def test_0003_count_and_keyset_pages(db, two_users):
    _needs(db, "users", "token_version", "0003")
    amir = two_users[0]["id"]
    table = ScopedTable(db, "transactions")
    rows = [
        {"date": d, "amount_sen": 100, "type": "expense", "category": "Food"}
        for d in ["2026-01-05"] * 3 + ["2026-01-04"] * 2
    ]
    table.insert_many(amir, rows)
    assert table.count(amir) == 5
    first = table.page_before(
        amir, between={"date": (None, None)}, order_by="date", after=None, limit=3
    )
    last = first[-1]
    rest = table.page_before(
        amir, between={"date": (None, None)}, order_by="date", after=(last["date"], last["id"]),
        limit=10,
    )  # fmt: skip
    assert len({r["id"] for r in first + rest}) == 5


def test_0004_budgets_are_unique_per_category_case_insensitively(db, two_users):
    _needs(db, "budgets", "id", "0004")
    amir, siti = (u["id"] for u in two_users)
    budgets.set_budget(db, amir, "Food", 1000)
    budgets.set_budget(db, amir, "Food", 2000)
    with pytest.raises(APIError):
        ScopedTable(db, "budgets").insert(amir, {"category": "FOOD", "limit_sen": 5})
    assert budgets.find(db, siti, "Food") is None
    assert [r["limit_sen"] for r in budgets.list_budgets(db, amir)] == [2000]
