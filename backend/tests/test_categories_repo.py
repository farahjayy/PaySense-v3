import pytest

from app.db import categories as repo
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


def spend(db, user, category, *, amount_sen=1000, **extra):
    return transactions.create(
        db,
        user,
        date="2026-06-10",
        amount_sen=amount_sen,
        type="expense",
        category=category,
        **extra,
    )


# ---------------------------------------------------------------- user_categories
def test_add_stores_the_cleaned_name_for_that_user(db, amir):
    row = repo.add(db, amir, "  Gym   class ")

    assert (row["user_id"], row["name"]) == (amir, "Gym class")
    assert repo.names(db, amir) == ["Gym class"]


def test_names_are_listed_alphabetically_and_only_for_the_caller(db, amir, siti):
    repo.add(db, amir, "Zakat")
    repo.add(db, amir, "gym")
    repo.add(db, siti, "Pets")

    assert repo.names(db, amir) == ["gym", "Zakat"]
    assert repo.names(db, siti) == ["Pets"]


def test_two_users_can_each_have_a_category_with_the_same_name(db, amir, siti):
    repo.add(db, amir, "Gym")

    repo.add(db, siti, "Gym")

    assert repo.names(db, siti) == ["Gym"]


def test_the_same_name_in_another_case_is_a_duplicate(db, amir):
    repo.add(db, amir, "Gym")

    with pytest.raises(repo.DuplicateCategory):
        repo.add(db, amir, "GYM")


@pytest.mark.parametrize("name", ["Food", "food", "Refund", "BNPL"])
def test_a_built_in_name_cannot_be_added(db, amir, name):
    with pytest.raises(repo.DuplicateCategory):
        repo.add(db, amir, name)


@pytest.mark.parametrize("name", ["", "123", "x" * 41])
def test_an_unusable_name_is_refused(db, amir, name):
    with pytest.raises(ValueError):
        repo.add(db, amir, name)


def test_rename_changes_the_name(db, amir):
    repo.add(db, amir, "Gym")

    row = repo.rename(db, amir, "Gym", "Fitness")

    assert row is not None and row["name"] == "Fitness"
    assert repo.names(db, amir) == ["Fitness"]


def test_rename_to_a_name_already_taken_is_a_duplicate(db, amir):
    repo.add(db, amir, "Gym")
    repo.add(db, amir, "Fitness")

    with pytest.raises(repo.DuplicateCategory):
        repo.rename(db, amir, "Gym", "fitness")


def test_a_name_can_change_only_its_case(db, amir):
    repo.add(db, amir, "gym")

    assert repo.rename(db, amir, "gym", "Gym")["name"] == "Gym"


def test_rename_of_a_category_that_was_never_added_is_none(db, amir):
    assert repo.rename(db, amir, "Nope", "Other thing") is None


def test_rename_cannot_touch_another_users_category(db, amir, siti):
    repo.add(db, siti, "Pets")

    assert repo.rename(db, amir, "Pets", "Cats") is None
    assert repo.names(db, siti) == ["Pets"]


def test_remove_deletes_only_the_callers_category(db, amir, siti):
    repo.add(db, amir, "Gym")
    repo.add(db, siti, "Gym")

    assert repo.remove(db, amir, "Gym") is True
    assert repo.names(db, amir) == []
    assert repo.names(db, siti) == ["Gym"]


def test_removing_what_was_never_added_is_false(db, amir):
    assert repo.remove(db, amir, "Gym") is False


@pytest.mark.parametrize("call", [repo.names, lambda db, uid: repo.add(db, uid, "Gym")])
@pytest.mark.parametrize("bad", ["", None, "   "])
def test_every_function_needs_a_user_id(db, call, bad):
    with pytest.raises(ValueError):
        call(db, bad)


# ---------------------------------------------------------------- the transactions side
def test_category_counts_are_per_user(db, amir, siti):
    spend(db, amir, "Food")
    spend(db, amir, "Food")
    spend(db, amir, "Gym")
    spend(db, siti, "Food")

    assert transactions.category_counts(db, amir) == {"Food": 2, "Gym": 1}
    assert transactions.category_counts(db, siti) == {"Food": 1}


def test_recategorise_moves_only_the_callers_rows_and_says_how_many(db, amir, siti):
    spend(db, amir, "Gym")
    spend(db, amir, "Gym")
    spend(db, amir, "Food")
    spend(db, siti, "Gym")

    moved = transactions.recategorise(db, amir, "Gym", "Fitness")

    assert moved == 2
    assert transactions.category_counts(db, amir) == {"Fitness": 2, "Food": 1}
    assert transactions.category_counts(db, siti) == {"Gym": 1}


@pytest.mark.parametrize("old", ["Food", "refund", "Transfer", "BNPL"])
def test_a_built_in_category_cannot_be_moved_away_from(db, amir, old):
    spend(db, amir, "Food")

    with pytest.raises(ValueError):
        transactions.recategorise(db, amir, old, "Gym")


def test_nothing_can_be_moved_into_the_bnpl_category(db, amir):
    spend(db, amir, "Gym")

    with pytest.raises(ValueError):
        transactions.recategorise(db, amir, "Gym", "bnpl")


def test_recategorise_to_the_same_name_does_nothing(db, amir):
    spend(db, amir, "Gym")

    assert transactions.recategorise(db, amir, "Gym", "Gym") == 0
