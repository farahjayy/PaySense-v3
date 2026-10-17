from datetime import UTC, datetime, timedelta

import jwt
import pytest
from fastapi.testclient import TestClient

from app.api.rate_limit import LoginRateLimiter
from app.db import user_settings, users
from app.main import create_app
from tests.fakes import FakeSupabase

PASSPHRASE = "correct horse battery staple"


@pytest.fixture
def db() -> FakeSupabase:
    fake = FakeSupabase()
    amir = users.create(fake, username="amir", display_name="Amir", persona="frequent_bnpl")
    users.set_passphrase(fake, amir["id"], PASSPHRASE)
    user_settings.create_default(fake, amir["id"])
    return fake


@pytest.fixture
def client(settings, db) -> TestClient:
    return TestClient(create_app(settings, db=db))


def _login(client: TestClient, username: str, passphrase: str = PASSPHRASE):
    return client.post("/api/auth/login", json={"username": username, "passphrase": passphrase})


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
    assert res.json()["detail"]["code"] == "invalid_credentials"


def test_a_wrong_passphrase_gets_the_same_answer_as_an_unknown_user(client):
    wrong = _login(client, "amir", "correct horse battery stapler")
    unknown = _login(client, "nobody")

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_a_user_with_no_passphrase_cannot_log_in(client, db):
    bare = users.create(db, username="bare", display_name="Bare")
    user_settings.create_default(db, bare["id"])

    assert _login(client, "bare", "anything long enough").status_code == 401


def test_the_passphrase_is_required(client):
    res = client.post("/api/auth/login", json={"username": "amir"})

    assert res.status_code == 422


def test_logout_revokes_every_session_of_that_user(client):
    first = _login(client, "amir").json()["access_token"]
    second = _login(client, "amir").json()["access_token"]
    auth = {"Authorization": f"Bearer {first}"}

    assert client.post("/api/auth/logout", headers=auth).status_code == 204
    for token in (first, second):
        res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 401
    fresh = _login(client, "amir").json()["access_token"]
    assert (
        client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh}"}).status_code == 200
    )


def test_logout_needs_a_session(client):
    assert client.post("/api/auth/logout").status_code == 401


def test_a_token_without_a_version_is_refused(client, db, settings):
    amir = users.get_by_username(db, "amir")
    old_style = jwt.encode(
        {"sub": amir["id"], "iss": "paysense-api", "exp": datetime.now(UTC) + timedelta(hours=1)},
        settings.session_secret.get_secret_value(),
        algorithm="HS256",
    )

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_style}"})

    assert res.status_code == 401


def test_repeated_failures_on_one_username_block_that_username_from_that_address(settings, db):
    per_user = LoginRateLimiter(max_failures=3, window_seconds=60)
    client = TestClient(create_app(settings, db=db, username_limiter=per_user))

    for n in range(3):
        _login(client, "amir", f"wrong passphrase {n}")
    res = client.post("/api/auth/login", json={"username": "AMIR", "passphrase": PASSPHRASE})

    assert res.status_code == 429
    assert res.json()["detail"]["code"] == "too_many_attempts"


def test_a_stranger_cannot_lock_the_owner_out_from_another_address(settings, db):
    """WP8 review finding 6: the username block is per (username, address)."""
    per_user = LoginRateLimiter(max_failures=3, window_seconds=60)
    client = TestClient(create_app(settings, db=db, username_limiter=per_user))

    elsewhere = TestClient(client.app, client=("9.9.9.9", 50000))

    for n in range(3):
        _login(client, "amir", f"wrong passphrase {n}")

    assert _login(client, "amir").status_code == 429
    assert _login(elsewhere, "amir").status_code == 200


def test_an_attempt_is_counted_before_the_passphrase_is_checked():
    """WP8 review finding 6: parallel attempts cannot all pass the check before any is recorded."""
    limiter = LoginRateLimiter(max_failures=2, window_seconds=60)
    assert limiter.attempt("k") and limiter.attempt("k")
    assert not limiter.attempt("k")
    limiter.forgive("k")
    assert limiter.attempt("k")


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
        settings.session_secret.get_secret_value(),
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


def test_spoofed_forwarded_for_does_not_change_the_rate_limit_bucket(settings, db):
    limiter = LoginRateLimiter(max_failures=2, window_seconds=60)
    client = TestClient(create_app(settings, db=db, login_limiter=limiter))

    body = {"username": "nobody", "passphrase": PASSPHRASE}
    first = client.post("/api/auth/login", json=body)
    spoofed = client.post("/api/auth/login", json=body, headers={"X-Forwarded-For": "9.9.9.9"})
    blocked = client.post("/api/auth/login", json=body, headers={"X-Forwarded-For": "8.8.8.8"})

    assert (first.status_code, spoofed.status_code, blocked.status_code) == (401, 401, 429)


def test_rate_limited_response_says_when_to_retry(settings, db):
    limiter = LoginRateLimiter(max_failures=1, window_seconds=90)
    client = TestClient(create_app(settings, db=db, login_limiter=limiter))
    _login(client, "nobody")

    res = _login(client, "nobody")

    assert res.status_code == 429
    assert res.headers["retry-after"] == "90"


def test_unknown_and_malformed_usernames_get_the_same_answer(client):
    unknown = _login(client, "nobody")
    malformed = _login(client, "no body!")

    assert unknown.status_code == malformed.status_code == 401
    assert unknown.json() == malformed.json()


def test_login_requests_are_bucketed_per_ipv6_prefix():
    from app.api.auth import client_key

    class _Req:
        def __init__(self, host):
            self.client = type("C", (), {"host": host})()

    a = client_key(_Req("2001:db8:aaaa:bbbb:1::1"))
    b = client_key(_Req("2001:db8:aaaa:bbbb:ffff::2"))
    c = client_key(_Req("2001:db8:aaaa:cccc::1"))

    assert a == b
    assert a != c
    assert client_key(_Req("203.0.113.5")) == "203.0.113.5"


def test_limiter_memory_is_bounded_when_keys_keep_changing():
    now = [0.0]
    limiter = LoginRateLimiter(
        max_failures=5, window_seconds=60, max_keys=100, clock=lambda: now[0]
    )

    for n in range(1000):
        limiter.record_failure(f"key-{n}")

    assert limiter.tracked_keys() <= 100
