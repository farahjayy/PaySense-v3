"""Session tokens (ADR D-03): HS256 bearer tokens carrying only the user id."""

from datetime import UTC, datetime, timedelta

import jwt

from app.core.settings import Settings

ALGORITHM = "HS256"
ISSUER = "paysense-api"


class InvalidTokenError(Exception):
    """The token is malformed, forged, expired, or lacks a required claim."""


def create_access_token(
    user_id: str, settings: Settings, now: datetime | None = None
) -> tuple[str, datetime]:
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(hours=settings.session_ttl_hours)
    claims = {"sub": user_id, "iss": ISSUER, "iat": issued_at, "exp": expires_at}
    return jwt.encode(claims, settings.session_secret, algorithm=ALGORITHM), expires_at


def decode_access_token(token: str, settings: Settings, now: datetime | None = None) -> str:
    """Return the user id in a valid token; raise InvalidTokenError otherwise.

    Only HS256 is accepted (so `alg: none` and key-confusion tokens fail), and `exp`, `sub` and
    `iss` are all required. Expiry is checked here against `now` so it can be tested exactly.
    """
    try:
        claims = jwt.decode(
            token,
            settings.session_secret,
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "sub", "iss"], "verify_exp": False},
        )
    except jwt.PyJWTError as err:
        raise InvalidTokenError(str(err)) from err
    current = (now or datetime.now(UTC)).timestamp()
    if claims["exp"] <= current:
        raise InvalidTokenError("token has expired")
    return claims["sub"]
