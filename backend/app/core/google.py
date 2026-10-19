"""Sign in with Google (ADR D-69): the OpenID Connect authorization-code flow with PKCE, built
directly on `httpx`. The rules are `GOOGLE_AUTH_PORTABLE.md` §2; this module holds the protocol
pieces, `api/google_auth.py` the routes.

The ID token's signature is not checked: it comes straight from Google's token endpoint over TLS,
which OIDC Core §3.1.3.7 accepts in place of a signature check. An ID token from anywhere else
(the browser) must never reach `check_claims`.
"""

import base64
import hashlib
import secrets
import time
from threading import Lock
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.core.settings import Settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105 (an endpoint, not a secret)
ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
SCOPES = "openid email profile"  # no Google verification review needed for these
CALLBACK_PATH = "/api/auth/google/callback"


class GoogleError(Exception):
    """The code exchange failed, or the ID token failed a check."""


def random_token() -> str:
    return secrets.token_urlsafe(32)  # 43 characters: also a valid PKCE verifier (RFC 7636)


def sha256_b64url(value: str) -> str:
    digest = hashlib.sha256(value.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def redirect_uri(settings: Settings) -> str:
    return f"{(settings.api_public_url or '').rstrip('/')}{CALLBACK_PATH}"


def authorization_url(settings: Settings, *, state: str, nonce: str, verifier: str) -> str:
    query = {
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri(settings),
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": sha256_b64url(verifier),
        "code_challenge_method": "S256",
        "prompt": "select_account",
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def exchange_code(
    settings: Settings, code: str, verifier: str, transport: httpx.BaseTransport | None = None
) -> str:
    """Trade the one-time code for an ID token, server to server, with the client secret."""
    secret = settings.google_client_secret
    data = {
        "code": code,
        "client_id": settings.google_client_id or "",
        "client_secret": secret.get_secret_value() if secret else "",
        "redirect_uri": redirect_uri(settings),
        "grant_type": "authorization_code",
        "code_verifier": verifier,
    }
    try:
        with httpx.Client(transport=transport, timeout=10) as client:
            res = client.post(TOKEN_URL, data=data)
        res.raise_for_status()
        token = res.json()["id_token"]
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as err:
        raise GoogleError("exchange") from err
    if not isinstance(token, str):
        raise GoogleError("exchange")
    return token


def check_claims(
    id_token: str, settings: Settings, nonce: str, now: float | None = None
) -> dict[str, Any]:
    try:
        claims = jwt.decode(id_token, options={"verify_signature": False})
    except jwt.PyJWTError as err:
        raise GoogleError("token") from err
    exp = claims.get("exp")
    valid = (
        claims.get("iss") in ISSUERS
        and claims.get("aud") == settings.google_client_id
        and isinstance(exp, int | float)
        and not isinstance(exp, bool)
        and exp > (now if now is not None else time.time())
        and bool(nonce)
        and secrets.compare_digest(str(claims.get("nonce", "")), nonce)
        and claims.get("email_verified") is True
        and isinstance(claims.get("sub"), str)
        and bool(claims["sub"])
        and isinstance(claims.get("email"), str)
    )
    if not valid:
        raise GoogleError("token")
    return claims


class HandoffStore:
    """One-time codes that carry a finished sign-in from the API's callback to the frontend.

    The frontend and the API are on different origins, so the callback cannot set a session the
    frontend can use, and a bearer token must never sit in a URL. Only the SHA-256 of a code is
    kept; a code works once, within `ttl_seconds`.
    """

    # ponytail: in memory on one process (ASSUMED 62); a second API instance needs a shared store
    def __init__(self, ttl_seconds: float = 60, max_codes: int = 10_000) -> None:
        self._ttl = ttl_seconds
        self._max = max_codes
        self._codes: dict[str, tuple[str, float]] = {}
        self._lock = Lock()

    def issue(self, user_id: str, now: float | None = None) -> str:
        stamp = now if now is not None else time.monotonic()
        code = random_token()
        with self._lock:
            self._codes = {k: v for k, v in self._codes.items() if v[1] > stamp}
            while len(self._codes) >= self._max:
                del self._codes[next(iter(self._codes))]
            self._codes[sha256_b64url(code)] = (user_id, stamp + self._ttl)
        return code

    def take(self, code: str, now: float | None = None) -> str | None:
        stamp = now if now is not None else time.monotonic()
        with self._lock:
            entry = self._codes.pop(sha256_b64url(code), None)
        if entry is None or entry[1] <= stamp:
            return None
        return entry[0]
