"""The protocol pieces of Google sign-in (ADR D-69) that the route tests do not reach."""

import httpx
import pytest
from pydantic import SecretStr

from app.core import google
from app.db import auth_events
from tests.fakes import FakeSupabase


@pytest.fixture
def gsettings(settings):
    return settings.model_copy(
        update={
            "google_client_id": "cid",
            "google_client_secret": SecretStr("s"),
            "api_public_url": "https://api.example.test",
        }  # fmt: skip
    )


@pytest.mark.parametrize("token", ["not-a-jwt", "a.b", ""])
def test_a_malformed_id_token_fails_the_check(gsettings, token):
    with pytest.raises(google.GoogleError):
        google.check_claims(token, gsettings, "nonce")


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="not json"),
        httpx.Response(200, json={"access_token": "x"}),
        httpx.Response(200, json={"id_token": 42}),
        httpx.Response(500),
    ],
)
def test_a_bad_token_endpoint_answer_is_an_exchange_failure(gsettings, response):
    transport = httpx.MockTransport(lambda request: response)
    with pytest.raises(google.GoogleError):
        google.exchange_code(gsettings, "code", "verifier", transport=transport)


def test_the_redirect_uri_is_the_api_origin_plus_the_callback(gsettings):
    assert google.redirect_uri(gsettings) == "https://api.example.test/api/auth/google/callback"


def test_settings_turn_google_on_only_when_complete(settings, gsettings):
    assert not settings.google_enabled
    assert gsettings.google_enabled
    assert settings.frontend_url == "http://localhost:3000"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"event": "nope"},
        {"event": "login", "reason": "state"},
        {"event": "login_failed"},
        {"event": "login_failed", "reason": "made-up"},
    ],  # fmt: skip
)
def test_an_auth_event_must_be_known_and_carry_a_reason_only_on_failure(kwargs):
    with pytest.raises(ValueError):
        auth_events.record(FakeSupabase(), kwargs.pop("event"), **kwargs)
