import pytest

from app.db import user_settings
from app.seed import seed_user
from tests.fakes import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    return FakeSupabase()


def test_seed_creates_the_user_and_default_settings(db):
    user, created = seed_user(db, username="amir", display_name="Amir", persona="frequent_bnpl")

    assert created is True
    assert user["username"] == "amir"
    assert user_settings.get(db, user["id"])["onboarding_state"] == "new"


def test_seed_is_idempotent(db):
    first, _ = seed_user(db, username="amir", display_name="Amir", persona="frequent_bnpl")

    second, created = seed_user(db, username="AMIR", display_name="Amir", persona="frequent_bnpl")

    assert created is False
    assert second["id"] == first["id"]
    assert len(db.rows("users")) == 1
    assert len(db.rows("user_settings")) == 1


def test_seed_repairs_a_user_that_has_no_settings_row(db):
    first, _ = seed_user(db, username="amir", display_name="Amir", persona=None)
    db.tables["user_settings"].clear()

    seed_user(db, username="amir", display_name="Amir", persona=None)

    assert user_settings.get(db, first["id"]) is not None


def test_seed_rejects_a_bad_persona(db):
    with pytest.raises(ValueError, match="persona"):
        seed_user(db, username="amir", display_name="Amir", persona="whale")


def test_seed_with_a_passphrase_lets_the_user_log_in_and_reseeding_replaces_it(db):
    from app.core.passphrase import verify_passphrase
    from app.db import users

    seed_user(
        db, username="amir", display_name="Amir", persona=None, passphrase="first passphrase!"
    )
    first = users.get_by_username(db, "amir")
    assert verify_passphrase(first["passphrase_hash"], "first passphrase!")

    seed_user(
        db, username="amir", display_name="Amir", persona=None, passphrase="second one, longer"
    )
    second = users.get_by_username(db, "amir")
    assert not verify_passphrase(second["passphrase_hash"], "first passphrase!")
    assert verify_passphrase(second["passphrase_hash"], "second one, longer")
    assert second["token_version"] > first["token_version"]  # old sessions end


def test_seed_without_a_passphrase_leaves_an_account_that_cannot_log_in(db):
    user, _ = seed_user(db, username="amir", display_name="Amir", persona=None)
    assert user.get("passphrase_hash") is None
