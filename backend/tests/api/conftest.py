"""Fixtures for HTTP-level tests: the real app on the in-memory database, two logged-in users."""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.seed import seed_user
from tests.fakes import TEST_PASSPHRASE, FakeSupabase, give_test_passphrase


@pytest.fixture
def fake_db() -> FakeSupabase:
    db = FakeSupabase()
    seed_user(db, username="amir", display_name="Amir", persona="frequent_bnpl")
    seed_user(db, username="siti", display_name="Siti", persona="budget_conscious")
    give_test_passphrase(db, "amir")
    give_test_passphrase(db, "siti")
    return db


@pytest.fixture
def api(settings, fake_db) -> TestClient:
    return TestClient(create_app(settings, db=fake_db))


def _headers(client: TestClient, username: str) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": username, "passphrase": TEST_PASSPHRASE})
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def amir(api) -> dict[str, str]:
    return _headers(api, "amir")


@pytest.fixture
def siti(api) -> dict[str, str]:
    return _headers(api, "siti")
