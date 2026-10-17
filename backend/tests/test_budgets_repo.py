"""Budgets repository: user-scoped, one per category (case-insensitive)."""

import pytest

from app.db import budgets, users
from tests.fakes import FakeSupabase


@pytest.fixture
def db():
    fake = FakeSupabase()
    for name in ("amir", "siti"):
        users.create(fake, username=name, display_name=name.title())
    return fake


def uid(db, name):
    return users.get_by_username(db, name)["id"]


def test_set_creates_then_replaces(db):
    a = uid(db, "amir")
    first = budgets.set_budget(db, a, "Food", 1000)
    second = budgets.set_budget(db, a, "Food", 2000)
    assert first["id"] == second["id"]
    assert [r["limit_sen"] for r in budgets.list_budgets(db, a)] == [2000]


def test_find_is_case_insensitive_and_scoped(db):
    a, s = uid(db, "amir"), uid(db, "siti")
    budgets.set_budget(db, a, "Drink/Dessert", 500)
    assert budgets.find(db, a, "drink/dessert")["limit_sen"] == 500
    assert budgets.find(db, s, "Drink/Dessert") is None


def test_delete_only_touches_the_callers_budget(db):
    a, s = uid(db, "amir"), uid(db, "siti")
    budgets.set_budget(db, a, "Food", 1000)
    budgets.set_budget(db, s, "Food", 1000)
    assert budgets.delete_budget(db, s, "Food")
    assert budgets.find(db, a, "Food") is not None
    assert not budgets.delete_budget(db, s, "Food")


@pytest.mark.parametrize("bad", [0, -1, 1.5, True, "10"])
def test_a_bad_limit_is_refused_before_the_database(db, bad):
    with pytest.raises(ValueError):
        budgets.set_budget(db, uid(db, "amir"), "Food", bad)


def test_user_id_is_required(db):
    with pytest.raises(ValueError):
        budgets.list_budgets(db, "")
