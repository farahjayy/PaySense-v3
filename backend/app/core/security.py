"""Session tokens (ADR D-03, D-49): HS256 bearer tokens carrying the user id and the user's token
version. Logging out raises the version, so every older token is refused."""

from datetime import UTC, datetime, timedelta

import jwt

from app.core.settings import Settings

ALGORITHM = "HS256"
ISSUER = "paysense-api"


class InvalidTokenError(Exception):
    """The token is malformed, forged, expired, or lacks a required claim."""


def create_access_token(
    user_id: str, settings: Settings, now: datetime | None = None, version: int = 0
) -> tuple[str, datetime]:
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + timedelta(hours=settings.session_ttl_hours)
    claims = {"sub": user_id, "iss": ISSUER, "iat": issued_at, "exp": expires_at, "ver": version}
    key = settings.session_secret.get_secret_value()
    return jwt.encode(claims, key, algorithm=ALGORITHM), expires_at


def decode_access_token(
    token: str, settings: Settings, now: datetime | None = None
) -> tuple[str, int]:
    """Return (user id, token version) from a valid token; raise InvalidTokenError otherwise.

    Only HS256 is accepted (so `alg: none` and key-confusion tokens fail), and `exp`, `sub`,
    `iss` and `ver` are all required. Expiry is checked here against `now` so it can be tested
    exactly.
    """
    try:
        claims = jwt.decode(
            token,
            settings.session_secret.get_secret_value(),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
            options={"require": ["exp", "sub", "iss", "ver"], "verify_exp": False},
        )
    except jwt.PyJWTError as err:
        raise InvalidTokenError(str(err)) from err
    expiry = claims["exp"]
    if isinstance(expiry, bool) or not isinstance(expiry, int | float):
        raise InvalidTokenError("exp claim must be a number")
    if expiry <= (now or datetime.now(UTC)).timestamp():
        raise InvalidTokenError("token has expired")
    version = claims["ver"]
    if isinstance(version, bool) or not isinstance(version, int):
        raise InvalidTokenError("ver claim must be an integer")
    return claims["sub"], version


def token_issued_at(token: str, settings: Settings) -> float:
    """When a valid token was issued (seconds since the epoch). Only call it on a token that
    `decode_access_token` has already accepted."""
    claims = jwt.decode(
        token,
        settings.session_secret.get_secret_value(),
        algorithms=[ALGORITHM],
        issuer=ISSUER,
        options={"verify_exp": False},
    )
    issued = claims.get("iat")
    if isinstance(issued, bool) or not isinstance(issued, int | float):
        raise InvalidTokenError("iat claim must be a number")
    return float(issued)
