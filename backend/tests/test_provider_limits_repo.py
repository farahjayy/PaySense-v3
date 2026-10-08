import pytest

from app.db import provider_limits as repo
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


def test_upsert_creates_a_limit(db, amir):
    row = repo.upsert_limit(db, amir, "spaylater", 250000)

    assert (row["user_id"], row["provider"], row["limit_sen"]) == (amir, "spaylater", 250000)
    assert repo.get_limit(db, amir, "spaylater") == 250000


def test_upserting_again_replaces_the_value_and_leaves_one_row(db, amir):
    repo.upsert_limit(db, amir, "spaylater", 250000)

    repo.upsert_limit(db, amir, "spaylater", 300000)

    assert repo.get_limit(db, amir, "spaylater") == 300000
    assert len(repo.list_limits(db, amir)) == 1


def test_limits_are_per_provider(db, amir):
    repo.upsert_limit(db, amir, "spaylater", 20000)
    repo.upsert_limit(db, amir, "atome", 50000)

    assert {r["provider"]: r["limit_sen"] for r in repo.list_limits(db, amir)} == {
        "spaylater": 20000,
        "atome": 50000,
    }
    assert repo.get_limit(db, amir, "tiktok_paylater") is None


@pytest.mark.parametrize("bad", [0, -1, 12.5, True, None])
def test_the_limit_must_be_a_positive_whole_number_of_sen(db, amir, bad):
    with pytest.raises(ValueError, match="limit_sen"):
        repo.upsert_limit(db, amir, "spaylater", bad)

    assert repo.list_limits(db, amir) == []


@pytest.mark.parametrize("provider", ["grab_paylater", "", "SPAYLATER"])
def test_the_provider_must_be_one_of_the_known_keys(db, amir, provider):
    with pytest.raises(ValueError, match="provider"):
        repo.upsert_limit(db, amir, provider, 1000)


def test_delete_removes_only_that_provider(db, amir):
    repo.upsert_limit(db, amir, "spaylater", 20000)
    repo.upsert_limit(db, amir, "atome", 50000)

    assert repo.delete_limit(db, amir, "spaylater") is True
    assert repo.delete_limit(db, amir, "spaylater") is False
    assert [r["provider"] for r in repo.list_limits(db, amir)] == ["atome"]


# ------------------------------------------------------------------ isolation (one per function)
def test_isolation_list_limits(db, amir, siti):
    repo.upsert_limit(db, amir, "spaylater", 20000)

    assert repo.list_limits(db, siti) == []


def test_isolation_get_limit(db, amir, siti):
    repo.upsert_limit(db, amir, "spaylater", 20000)

    assert repo.get_limit(db, siti, "spaylater") is None


def test_isolation_upsert_never_touches_another_users_row(db, amir, siti):
    repo.upsert_limit(db, amir, "spaylater", 20000)

    repo.upsert_limit(db, siti, "spaylater", 99999)

    assert repo.get_limit(db, amir, "spaylater") == 20000
    assert repo.get_limit(db, siti, "spaylater") == 99999
    assert len(db.rows("provider_limits")) == 2


def test_isolation_delete(db, amir, siti):
    repo.upsert_limit(db, amir, "spaylater", 20000)

    assert repo.delete_limit(db, siti, "spaylater") is False
    assert repo.get_limit(db, amir, "spaylater") == 20000


@pytest.mark.parametrize("bad", [None, "", "  "])
def test_every_function_requires_a_user_id(db, bad):
    for call in (
        lambda: repo.list_limits(db, bad),
        lambda: repo.get_limit(db, bad, "atome"),
        lambda: repo.upsert_limit(db, bad, "atome", 100),
        lambda: repo.delete_limit(db, bad, "atome"),
    ):
        with pytest.raises(ValueError, match="user_id"):
            call()
