import pytest

from app.db import user_settings
from app.db.users import UsernameTakenError, create, get_by_id, get_by_username
from tests.fakes import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    return FakeSupabase()


def test_create_then_lookup_by_username(db):
    user = create(db, username="amir", display_name="Amir", persona="frequent_bnpl")

    found = get_by_username(db, "amir")

    assert found["id"] == user["id"]
    assert found["persona"] == "frequent_bnpl"


def test_lookup_is_case_insensitive_and_trims(db):
    user = create(db, username="Amir", display_name="Amir")

    assert get_by_username(db, "  aMIR ")["id"] == user["id"]


def test_unknown_username_returns_none(db):
    assert get_by_username(db, "nobody") is None


@pytest.mark.parametrize("hostile", ["%", "a%", "_mir", "amir%", "x' or '1'='1", "", "   "])
def test_wildcards_and_junk_never_match_a_user(db, hostile):
    create(db, username="amir", display_name="Amir")

    assert get_by_username(db, hostile) is None


def test_duplicate_username_is_rejected_case_insensitively(db):
    create(db, username="amir", display_name="Amir")

    with pytest.raises(UsernameTakenError):
        create(db, username="AMIR", display_name="Other Amir")


def test_invalid_username_is_rejected_on_create(db):
    with pytest.raises(ValueError, match="username"):
        create(db, username="has space", display_name="X")


def test_get_by_id(db):
    user = create(db, username="amir", display_name="Amir")

    assert get_by_id(db, user["id"])["username"] == "amir"
    assert get_by_id(db, "00000000-0000-0000-0000-000000000000") is None


def test_default_settings_are_created_with_ledger_mode_on(db):
    user = create(db, username="amir", display_name="Amir")

    settings = user_settings.create_default(db, user["id"])

    assert settings["ledger_mode"] is True
    assert settings["current_balance_sen"] == 0
    assert user_settings.get(db, user["id"])["onboarding_state"] == "new"


def test_create_default_settings_is_idempotent(db):
    user = create(db, username="amir", display_name="Amir")

    first = user_settings.create_default(db, user["id"])
    second = user_settings.create_default(db, user["id"])

    assert first["user_id"] == second["user_id"]
    assert len(db.rows("user_settings")) == 1
