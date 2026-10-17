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


def test_default_settings_are_created_without_any_balance(db):
    user = create(db, username="amir", display_name="Amir")

    settings = user_settings.create_default(db, user["id"])

    assert settings["onboarding_state"] == "new"
    # D-27: the forecast runs on flows, so there is no balance to store. D-50 adds only the
    # savings buffer the person chooses to record (0 until they do), never a synced balance.
    assert "balance" not in " ".join(settings)
    assert settings["savings_buffer_sen"] == 0
    assert settings["consent_version"] is None  # WP19: nobody has accepted the notice yet
    assert user_settings.get(db, user["id"])["onboarding_state"] == "new"


def test_create_default_settings_is_idempotent(db):
    user = create(db, username="amir", display_name="Amir")

    first = user_settings.create_default(db, user["id"])
    second = user_settings.create_default(db, user["id"])

    assert first["user_id"] == second["user_id"]
    assert len(db.rows("user_settings")) == 1


def test_onboarding_state_can_advance_and_rejects_unknown_states(db):
    user = create(db, username="amir", display_name="Amir")
    user_settings.create_default(db, user["id"])

    updated = user_settings.set_onboarding_state(db, user["id"], "history_imported")

    assert updated["onboarding_state"] == "history_imported"
    with pytest.raises(ValueError, match="onboarding_state"):
        user_settings.set_onboarding_state(db, user["id"], "finished")


def test_setting_the_onboarding_state_creates_the_row_if_it_is_missing(db):
    user = create(db, username="amir", display_name="Amir")

    updated = user_settings.set_onboarding_state(db, user["id"], "history_imported")

    assert updated["onboarding_state"] == "history_imported"
    assert len(db.rows("user_settings")) == 1


def test_setting_the_onboarding_state_only_touches_that_user(db):
    amir = create(db, username="amir", display_name="Amir")
    siti = create(db, username="siti", display_name="Siti")
    user_settings.create_default(db, siti["id"])

    user_settings.set_onboarding_state(db, amir["id"], "complete")

    assert user_settings.get(db, siti["id"])["onboarding_state"] == "new"
