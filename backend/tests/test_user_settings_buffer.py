"""The savings buffer setting (ADR D-50): per user, never negative, default 0."""

import pytest

from app.db import user_settings, users
from tests.fakes import FakeSupabase


@pytest.fixture
def db():
    fake = FakeSupabase()
    for name in ("amir", "siti"):
        user = users.create(fake, username=name, display_name=name.title())
        user_settings.create_default(fake, user["id"])
    return fake


def uid(db, name):
    return users.get_by_username(db, name)["id"]


def test_the_buffer_defaults_to_zero(db):
    assert user_settings.get_savings_buffer(db, uid(db, "amir")) == 0


def test_setting_the_buffer_is_per_user(db):
    user_settings.set_savings_buffer(db, uid(db, "amir"), 150_000)
    assert user_settings.get_savings_buffer(db, uid(db, "amir")) == 150_000
    assert user_settings.get_savings_buffer(db, uid(db, "siti")) == 0


def test_a_user_without_a_settings_row_reads_zero_and_can_set_one(db):
    lone = users.create(db, username="lone", display_name="Lone")
    assert user_settings.get_savings_buffer(db, lone["id"]) == 0
    user_settings.set_savings_buffer(db, lone["id"], 500)
    assert user_settings.get_savings_buffer(db, lone["id"]) == 500


@pytest.mark.parametrize("bad", [-1, 1.5, True, "100", None, 100_000_000_001])
def test_a_bad_buffer_is_refused_before_the_database(db, bad):
    with pytest.raises(ValueError):
        user_settings.set_savings_buffer(db, uid(db, "amir"), bad)
