from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.rate_limit import LoginRateLimiter
from app.db import user_settings, users
from app.main import create_app
from tests.fakes import FakeSupabase


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    amir = users.create(fake, username="amir", display_name="Amir", persona="frequent_bnpl")
    user_settings.create_default(fake, amir["id"])
    return fake


@pytest.fixture
def client(settings, db) -> TestClient:
    return TestClient(create_app(settings, db=db))


def _login(client: TestClient, username: str):
    return client.post("/api/auth/login", json={"username": username})


def test_login_returns_a_token_and_the_user(client):
    res = _login(client, "amir")

    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["expires_in"] == 12 * 3600
    assert body["user"]["username"] == "amir"
    assert body["user"]["display_name"] == "Amir"
    assert body["user"]["persona"] == "frequent_bnpl"


def test_login_is_case_insensitive(client):
    assert _login(client, "AMIR").status_code == 200


def test_unknown_username_is_401_with_the_envelope(client):
    res = _login(client, "nobody")

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "unknown_username"


@pytest.mark.parametrize("hostile", ["%", "a%", "x' or '1'='1", "   "])
def test_hostile_usernames_do_not_log_in(client, hostile):
    assert _login(client, hostile).status_code == 401


def test_missing_username_is_a_validation_error(client):
    res = client.post("/api/auth/login", json={})

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "validation_error"


def test_me_returns_the_logged_in_user(client):
    token = _login(client, "amir").json()["access_token"]

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 200
    assert res.json()["username"] == "amir"


def test_me_without_a_token_is_401(client):
    res = client.get("/api/auth/me")

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "not_authenticated"


def test_me_with_a_forged_token_is_401(client, settings):
    forged = jwt.encode(
        {"sub": "x", "iss": "paysense-api", "exp": datetime.now(UTC) + timedelta(hours=1)},
        "z" * 40,
        algorithm="HS256",
    )

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {forged}"})

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "invalid_token"


def test_me_with_an_expired_token_is_401(client, settings):
    expired = jwt.encode(
        {
            "sub": "x",
            "iss": "paysense-api",
            "exp": datetime.now(UTC) - timedelta(minutes=1),
        },
        settings.session_secret,
        algorithm="HS256",
    )

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired}"})

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "invalid_token"


def test_valid_token_for_a_deleted_user_is_401(client, db):
    token = _login(client, "amir").json()["access_token"]
    db.tables["users"].clear()

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert res.status_code == 401


def test_login_is_rate_limited_after_repeated_failures(settings, db):
    limiter = LoginRateLimiter(max_failures=3, window_seconds=60)
    client = TestClient(create_app(settings, db=db, login_limiter=limiter))

    statuses = [_login(client, "nobody").status_code for _ in range(4)]

    assert statuses == [401, 401, 401, 429]
    assert _login(client, "amir").status_code == 429  # blocked even with a valid name


def test_rate_limit_window_expires():
    now = [1000.0]
    limiter = LoginRateLimiter(max_failures=2, window_seconds=60, clock=lambda: now[0])

    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")
    assert limiter.is_blocked("1.2.3.4")

    now[0] += 61
    assert not limiter.is_blocked("1.2.3.4")


def test_successful_login_does_not_count_against_the_limit(settings, db):
    limiter = LoginRateLimiter(max_failures=2, window_seconds=60)
    client = TestClient(create_app(settings, db=db, login_limiter=limiter))

    assert all(_login(client, "amir").status_code == 200 for _ in range(5))
