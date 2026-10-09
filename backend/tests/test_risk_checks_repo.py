"""Frozen risk checks: stored once, read back unchanged, never visible to another user."""

import pytest

from app.db import risk_checks
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


def row(**overrides):
    base = {
        "input": {"provider": "spaylater"},
        "features": {"dsr_with_purchase": 0.4},
        "feature_schema_hash": "abc",
        "model_version": "v1",
        "p": 0.25,
        "p_simulated": 0.3,
        "score": 75,
        "label": "caution",
        "factors": [],
    }
    base.update(overrides)
    return base


def test_a_stored_check_reads_back_unchanged(db, two_users):
    amir, _ = two_users
    created = risk_checks.create(db, amir, row())

    found = risk_checks.get(db, amir, created["id"])
    assert found["p"] == 0.25 and found["input"] == {"provider": "spaylater"}
    assert found["user_id"] == amir


def test_another_user_cannot_read_or_delete_it(db, two_users):
    amir, siti = two_users
    created = risk_checks.create(db, amir, row())

    assert risk_checks.get(db, siti, created["id"]) is None
    assert risk_checks.delete(db, siti, created["id"]) is False
    assert risk_checks.get(db, amir, created["id"]) is not None


def test_a_malformed_id_finds_nothing(db, two_users):
    amir, _ = two_users
    assert risk_checks.get(db, amir, "not-a-uuid") is None


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"p": 1.2}, "probability"),
        ({"p_simulated": -0.1}, "probability"),
        ({"p": True}, "probability"),
        ({"score": 101}, "score"),
        ({"score": 50.5}, "score"),
        ({"label": "meh"}, "label"),
    ],
)
def test_values_outside_the_contract_are_refused_before_the_database(db, two_users, patch, message):
    amir, _ = two_users
    with pytest.raises(ValueError, match=message):
        risk_checks.create(db, amir, row(**patch))


def test_a_missing_field_is_refused(db, two_users):
    amir, _ = two_users
    incomplete = row()
    del incomplete["factors"]
    with pytest.raises(ValueError, match="factors"):
        risk_checks.create(db, amir, incomplete)


def test_the_user_id_comes_from_the_argument_never_the_row(db, two_users):
    amir, siti = two_users
    with pytest.raises(ValueError, match="user_id"):
        risk_checks.create(db, amir, row(user_id=siti))
