"""Fixtures for tests that talk to the REAL Supabase project (`uv run pytest -m integration`).

They skip cleanly when no credentials are configured. Each test gets two throwaway users with
random usernames; deleting a user cascades to every row it owns.
"""

import secrets

import pytest

from app.core.settings import MissingSettingsError, load_settings
from app.db import users
from app.db.client import build_client


@pytest.fixture(scope="session")
def db():
    try:
        settings = load_settings()
    except MissingSettingsError as err:
        pytest.skip(f"no Supabase credentials configured: {err}")
    return build_client(settings)


@pytest.fixture
def two_users(db):
    created = [
        users.create(db, username=f"it_{secrets.token_hex(6)}", display_name=f"IT {n}")
        for n in ("A", "B")
    ]
    yield created
    for user in created:
        db.table("users").delete().eq("id", user["id"]).execute()
