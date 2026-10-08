"""Two seeded users must never see each other's data (CLAUDE.md hard constraint 4)."""

import pytest
from fastapi.testclient import TestClient

from app.db import user_settings
from app.db.base import ScopedTable
from app.main import create_app
from app.seed import seed_user
from tests.fakes import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    return FakeSupabase()


@pytest.fixture
def client(settings, db) -> TestClient:
    seed_user(db, username="amir", display_name="Amir", persona="frequent_bnpl")
    seed_user(db, username="siti", display_name="Siti", persona="budget_conscious")
    return TestClient(create_app(settings, db=db))


def _login(client: TestClient, username: str) -> str:
    return client.post("/api/auth/login", json={"username": username}).json()["access_token"]


def _me(client: TestClient, credential: str) -> dict:
    return client.get("/api/auth/me", headers={"Authorization": f"Bearer {credential}"}).json()


def test_each_session_resolves_to_its_own_user(client):
    amir = _me(client, _login(client, "amir"))
    siti = _me(client, _login(client, "siti"))

    assert (amir["username"], siti["username"]) == ("amir", "siti")
    assert amir["id"] != siti["id"]


def test_each_user_has_exactly_one_settings_row(db, client):
    amir = _me(client, _login(client, "amir"))
    siti = _me(client, _login(client, "siti"))

    assert user_settings.get(db, amir["id"])["user_id"] == amir["id"]
    assert user_settings.get(db, siti["id"])["user_id"] == siti["id"]
    assert len(db.rows("user_settings")) == 2


def test_each_user_sees_only_their_own_rows_through_the_repository(db, client):
    amir = _me(client, _login(client, "amir"))["id"]
    siti = _me(client, _login(client, "siti"))["id"]
    transactions = ScopedTable(db, "transactions")
    row = {"date": "2026-01-05", "type": "expense", "category": "Food"}
    mine = transactions.insert(amir, {**row, "amount_sen": 1500})
    transactions.insert(siti, {**row, "amount_sen": 2500})

    assert [r["id"] for r in transactions.list_rows(amir)] == [mine["id"]]
    assert [r["amount_sen"] for r in transactions.list_rows(siti)] == [2500]


def test_tampered_credential_is_refused(client):
    genuine = _login(client, "amir")
    tampered = genuine[:-4] + ("AAAA" if not genuine.endswith("AAAA") else "BBBB")

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered}"})

    assert res.status_code == 401
