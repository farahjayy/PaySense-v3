"""Sign in with Google (ADR D-69): the OIDC code flow with PKCE, a one-time handoff code, and an
audit row for every sign-up, login, failed login and logout. Google's token endpoint is mocked."""

import base64
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.google import HandoffStore
from app.core.security import create_access_token
from app.db import users
from app.main import create_app
from tests.fakes import TEST_PASSPHRASE

CLIENT_ID = "client-id.apps.googleusercontent.com"
API = "https://api.example.test"
APP = "https://app.example.test"
SUB = "1234567890"


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()


def id_token(**overrides) -> str:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "exp": int(time.time()) + 300,
        "sub": SUB,
        "email": "nur@example.com",
        "email_verified": True,
        "name": "Nur",
    } | overrides
    return f"{_b64({'alg': 'RS256'})}.{_b64(claims)}.c2lnbmF0dXJl"


class FakeGoogle:
    """Google's token endpoint: answers with whatever ID token the test sets, records requests."""

    def __init__(self) -> None:
        self.claims: dict = {}
        self.status = 200
        self.requests: list[dict[str, list[str]]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(parse_qs(request.content.decode()))
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "invalid_grant"})
        nonce = self.claims.pop("nonce", None) or self.nonce
        return httpx.Response(200, json={"id_token": id_token(nonce=nonce, **self.claims)})


@pytest.fixture
def google_settings(settings):
    return settings.model_copy(
        update={
            "google_client_id": CLIENT_ID,
            "google_client_secret": SecretStr("test-client-secret"),
            "api_public_url": API,
            "app_url": APP,
        }
    )


@pytest.fixture
def google() -> FakeGoogle:
    return FakeGoogle()


@pytest.fixture
def gapi(google_settings, fake_db, google) -> TestClient:
    app = create_app(google_settings, db=fake_db)
    app.state.google_transport = httpx.MockTransport(google.handler)
    return TestClient(app, base_url=API, follow_redirects=False)


def start(client: TestClient, google: FakeGoogle) -> dict[str, str]:
    res = client.get("/api/auth/google")
    assert res.status_code == 302
    query = {k: v[0] for k, v in parse_qs(urlparse(res.headers["location"]).query).items()}
    google.nonce = query["nonce"]
    return query


def sign_in(client: TestClient, google: FakeGoogle) -> httpx.Response:
    query = start(client, google)
    return client.get(f"/api/auth/google/callback?code=abc&state={query['state']}")


def handoff(res: httpx.Response) -> str:
    location = res.headers["location"]
    assert location.startswith(f"{APP}/login#google=")
    return location.split("#google=", 1)[1]


def events(fake_db, kind=None):
    rows = fake_db.rows("auth_events")
    return [r for r in rows if kind is None or r["event"] == kind]


def test_without_google_settings_the_routes_are_not_there(api):
    assert api.get("/api/auth/google", follow_redirects=False).status_code == 404
    assert api.get("/api/auth/google/callback?code=x&state=y").status_code == 404
    assert api.post("/api/auth/google/exchange", json={"code": "x" * 43}).status_code == 404


def test_start_sends_the_browser_to_google_with_state_nonce_and_pkce(gapi, google):
    res = gapi.get("/api/auth/google")

    url = urlparse(res.headers["location"])
    query = {k: v[0] for k, v in parse_qs(url.query).items()}
    assert (
        f"{url.scheme}://{url.netloc}{url.path}" == "https://accounts.google.com/o/oauth2/v2/auth"
    )
    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == f"{API}/api/auth/google/callback"
    assert query["response_type"] == "code"
    assert query["scope"] == "openid email profile"
    assert query["code_challenge_method"] == "S256"
    cookie = res.headers["set-cookie"]
    flow = cookie.split(";", 1)[0].split("=", 1)[1]
    state, verifier, nonce = flow.split(".")
    assert query["state"] == state and query["nonce"] == nonce
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=")
    assert query["code_challenge"] == challenge.decode()
    lowered = cookie.lower()
    assert "httponly" in lowered and "samesite=lax" in lowered and "secure" in lowered
    assert "path=/api/auth/google" in lowered and "max-age=600" in lowered


def test_a_first_sign_in_creates_the_user_and_hands_over_a_session(gapi, google, fake_db):
    res = sign_in(gapi, google)

    code = handoff(res)
    assert "google_flow=" in res.headers["set-cookie"]  # the flow cookie is cleared
    exchanged = gapi.post("/api/auth/google/exchange", json={"code": code})
    assert exchanged.status_code == 200
    body = exchanged.json()
    me = gapi.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["display_name"] == "Nur"
    row = users.get_by_google_sub(fake_db, SUB)
    assert row["email"] == "nur@example.com"
    assert users.normalise_username(row["username"]) == row["username"]
    assert [e["event"] for e in events(fake_db)] == ["signup", "login"]
    assert all(e["user_id"] == row["id"] for e in events(fake_db))
    # the exchange sent the PKCE verifier and the secret, server to server
    sent = google.requests[0]
    assert sent["code_verifier"][0] and sent["client_secret"] == ["test-client-secret"]
    assert sent["grant_type"] == ["authorization_code"]


def test_the_handoff_code_works_once(gapi, google):
    code = handoff(sign_in(gapi, google))

    assert gapi.post("/api/auth/google/exchange", json={"code": code}).status_code == 200
    again = gapi.post("/api/auth/google/exchange", json={"code": code})
    assert again.status_code == 401
    assert again.json()["detail"]["code"] == "invalid_code"


def test_the_handoff_code_expires():
    store = HandoffStore(ttl_seconds=60)
    code = store.issue("user-1", now=1000.0)

    assert store.take(code, now=1061.0) is None
    assert store.take(store.issue("user-1", now=1000.0), now=1059.0) == "user-1"


def test_the_handoff_store_keeps_only_a_hash_of_the_code():
    store = HandoffStore()
    code = store.issue("user-1")

    assert code not in repr(store._codes)


def test_a_second_sign_in_reuses_the_account(gapi, google, fake_db):
    sign_in(gapi, google)
    google.claims = {"email": "nur.new@example.com"}
    sign_in(gapi, google)

    assert len([u for u in fake_db.rows("users") if u.get("google_sub") == SUB]) == 1
    assert users.get_by_google_sub(fake_db, SUB)["email"] == "nur.new@example.com"
    assert [e["event"] for e in events(fake_db)] == ["signup", "login", "login"]


def test_cancelling_on_google_returns_to_login_with_a_reason(gapi, google, fake_db):
    query = start(gapi, google)

    res = gapi.get(f"/api/auth/google/callback?error=access_denied&state={query['state']}")
    assert res.headers["location"] == f"{APP}/login?error=cancelled"
    assert [e["reason"] for e in events(fake_db, "login_failed")] == ["cancelled"]


def test_a_wrong_state_is_refused(gapi, google, fake_db):
    start(gapi, google)

    res = gapi.get("/api/auth/google/callback?code=abc&state=wrong")
    assert res.headers["location"] == f"{APP}/login?error=state"
    assert not google.requests  # no code exchange without a matching state
    assert [e["reason"] for e in events(fake_db, "login_failed")] == ["state"]


def test_a_callback_without_the_flow_cookie_is_refused(gapi, google):
    query = start(gapi, google)
    gapi.cookies.clear()

    res = gapi.get(f"/api/auth/google/callback?code=abc&state={query['state']}")
    assert res.headers["location"] == f"{APP}/login?error=state"


def test_a_failed_code_exchange_is_refused(gapi, google, fake_db):
    google.status = 400

    res = sign_in(gapi, google)
    assert res.headers["location"] == f"{APP}/login?error=exchange"
    assert users.get_by_google_sub(fake_db, SUB) is None


@pytest.mark.parametrize(
    "claims",
    [
        {"aud": "someone-else"},
        {"iss": "https://evil.example"},
        {"exp": int(time.time()) - 1},
        {"nonce": "not-the-nonce"},
        {"email_verified": False},
    ],
)
def test_an_id_token_that_fails_a_check_is_refused(gapi, google, fake_db, claims):
    google.claims = dict(claims)

    res = sign_in(gapi, google)
    assert res.headers["location"] == f"{APP}/login?error=token"
    assert users.get_by_google_sub(fake_db, SUB) is None
    assert [e["reason"] for e in events(fake_db, "login_failed")] == ["token"]


def test_failed_callbacks_are_rate_limited_per_address(google_settings, fake_db, google):
    from app.api.rate_limit import LoginRateLimiter

    app = create_app(google_settings, db=fake_db, login_limiter=LoginRateLimiter(max_failures=2))
    app.state.google_transport = httpx.MockTransport(google.handler)
    client = TestClient(app, base_url=API, follow_redirects=False)
    for _ in range(2):
        client.get("/api/auth/google/callback?code=abc&state=wrong")

    res = client.get("/api/auth/google/callback?code=abc&state=wrong")
    assert res.headers["location"] == f"{APP}/login?error=too_many"
    assert len(events(fake_db, "login_failed")) == 2  # the blocked one writes nothing


def test_a_google_account_cannot_sign_in_with_the_passphrase_form(gapi, google, fake_db):
    sign_in(gapi, google)
    name = users.get_by_google_sub(fake_db, SUB)["username"]

    res = gapi.post("/api/auth/login", json={"username": name, "passphrase": TEST_PASSPHRASE})
    assert res.status_code == 401


def test_logout_is_audited_and_ends_the_session(gapi, google, fake_db):
    token = gapi.post(
        "/api/auth/google/exchange", json={"code": handoff(sign_in(gapi, google))}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    assert gapi.post("/api/auth/logout", headers=headers).status_code == 204
    assert gapi.get("/api/auth/me", headers=headers).status_code == 401
    assert [e["event"] for e in events(fake_db)][-1] == "logout"


def test_auth_events_are_exported_and_deleted_with_my_data(gapi, google, fake_db):
    token = gapi.post(
        "/api/auth/google/exchange", json={"code": handoff(sign_in(gapi, google))}
    ).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    exported = gapi.post("/api/account/export", headers=headers).json()
    assert {e["event"] for e in exported["tables"]["auth_events"]} == {"signup", "login"}
    deleted = gapi.post(
        "/api/account/delete", headers=headers, json={"confirmation": "delete my data"}
    )
    assert deleted.status_code == 200
    uid = users.get_by_google_sub(fake_db, SUB)["id"]
    assert not [e for e in events(fake_db) if e["user_id"] == uid]


def test_a_google_account_deletes_only_from_a_fresh_sign_in(gapi, google, google_settings, fake_db):
    sign_in(gapi, google)
    uid = users.get_by_google_sub(fake_db, SUB)["id"]
    old = datetime.now(UTC) - timedelta(minutes=16)
    token, _ = create_access_token(uid, google_settings, now=old)
    headers = {"Authorization": f"Bearer {token}"}

    res = gapi.post("/api/account/delete", headers=headers, json={"confirmation": "delete my data"})
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "sign_in_again"


def test_a_passphrase_account_still_needs_its_passphrase_to_delete(api, amir):
    res = api.post("/api/account/delete", headers=amir, json={"confirmation": "delete my data"})

    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "wrong_passphrase"


def test_my_auth_events_never_appear_in_another_users_export(gapi, google, fake_db, siti):
    sign_in(gapi, google)

    exported = gapi.post("/api/account/export", headers=siti).json()
    assert exported["tables"]["auth_events"] == []
