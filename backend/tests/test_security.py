from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core.security import InvalidTokenError, create_access_token, decode_access_token

USER_ID = "7e332799-b907-41c9-9b70-5f7bef06c816"
ISSUER = "paysense-api"


def _claims(**overrides):
    return {
        "sub": USER_ID,
        "iss": ISSUER,
        "exp": datetime.now(UTC) + timedelta(hours=1),
        "ver": 0,
    } | overrides


def test_session_round_trips_user_id(settings):
    session, _ = create_access_token(USER_ID, settings)

    assert decode_access_token(session, settings) == (USER_ID, 0)


def test_session_expires_after_ttl(settings):
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    session, expires_at = create_access_token(USER_ID, settings, now=now)

    ttl = timedelta(hours=settings.session_ttl_hours)
    assert expires_at == now + ttl
    assert (
        decode_access_token(session, settings, now=now + ttl - timedelta(seconds=5))[0] == USER_ID
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(session, settings, now=now + ttl + timedelta(seconds=5))


def test_foreign_signature_rejected(settings):
    forged = jwt.encode(_claims(), "y" * 40, algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(forged, settings)


def test_alg_none_rejected(settings):
    unsigned = jwt.encode(_claims(), key=None, algorithm="none")

    with pytest.raises(InvalidTokenError):
        decode_access_token(unsigned, settings)


def test_missing_expiry_rejected(settings):
    claims = _claims()
    del claims["exp"]
    no_exp = jwt.encode(claims, settings.session_secret.get_secret_value(), algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(no_exp, settings)


def test_wrong_issuer_rejected(settings):
    other = jwt.encode(
        _claims(iss="someone-else"), settings.session_secret.get_secret_value(), algorithm="HS256"
    )

    with pytest.raises(InvalidTokenError):
        decode_access_token(other, settings)


def test_missing_subject_rejected(settings):
    claims = _claims()
    del claims["sub"]
    anonymous = jwt.encode(claims, settings.session_secret.get_secret_value(), algorithm="HS256")

    with pytest.raises(InvalidTokenError):
        decode_access_token(anonymous, settings)


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x"])
def test_garbage_is_rejected(settings, garbage):
    with pytest.raises(InvalidTokenError):
        decode_access_token(garbage, settings)


def test_the_token_carries_the_users_version(settings):
    session, _ = create_access_token(USER_ID, settings, version=7)

    assert decode_access_token(session, settings) == (USER_ID, 7)


@pytest.mark.parametrize("bad", [None, "1", 1.5, True])
def test_a_missing_or_non_integer_version_is_refused(settings, bad):
    claims = _claims()
    if bad is None:
        del claims["ver"]
    else:
        claims["ver"] = bad
    token = jwt.encode(claims, settings.session_secret.get_secret_value(), algorithm="HS256")
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings)
