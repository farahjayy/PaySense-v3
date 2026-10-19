"""Sign in with Google (ADR D-69). The browser navigates to `/api/auth/google`, Google sends it
back to the callback, and the callback hands the frontend a one-time code that it exchanges for
the same session as the passphrase login. Every failure goes back to the login page with a reason
and writes a `login_failed` audit row."""

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.auth import LimiterDep, client_key, session_for
from app.api.deps import DbDep, SettingsDep
from app.api.schemas import ERROR_RESPONSES, LoginResponse
from app.core import google
from app.core.errors import api_error, unauthorized
from app.core.settings import Settings
from app.db import auth_events, users

FLOW_COOKIE = "google_flow"
FLOW_PATH = "/api/auth/google"
FLOW_SECONDS = 600


def require_google(settings: SettingsDep) -> Settings:
    if not settings.google_enabled:
        raise api_error(404, "not_found", "Google sign-in is not set up on this server.")
    return settings


GoogleSettings = Annotated[Settings, Depends(require_google)]
router = APIRouter(prefix="/auth/google", tags=["auth"], responses=ERROR_RESPONSES)


class ExchangeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, max_length=100)


def _secure(settings: Settings) -> bool:
    return (settings.api_public_url or "").startswith("https://")


@router.get("", status_code=302, response_class=RedirectResponse)
def google_start(settings: GoogleSettings) -> RedirectResponse:
    """Send the browser to Google with a fresh state (CSRF), PKCE verifier and nonce (replay)."""
    state, verifier, nonce = google.random_token(), google.random_token(), google.random_token()
    url = google.authorization_url(settings, state=state, nonce=nonce, verifier=verifier)
    res = RedirectResponse(url, status_code=302)
    res.set_cookie(
        FLOW_COOKIE, f"{state}.{verifier}.{nonce}", max_age=FLOW_SECONDS, path=FLOW_PATH,
        httponly=True, secure=_secure(settings), samesite="lax",
    )  # fmt: skip
    return res


@router.get("/callback", status_code=302, response_class=RedirectResponse)
def google_callback(
    request: Request,
    settings: GoogleSettings,
    db: DbDep,
    limiter: LimiterDep,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    app_url = settings.frontend_url
    parts = request.cookies.get(FLOW_COOKIE, "").split(".")
    flow_state, verifier, nonce = parts if len(parts) == 3 else ("", "", "")
    key = client_key(request)
    agent = request.headers.get("user-agent")

    def go(location: str) -> RedirectResponse:
        res = RedirectResponse(location, status_code=302)
        res.delete_cookie(
            FLOW_COOKIE, path=FLOW_PATH, httponly=True, secure=_secure(settings), samesite="lax"
        )
        return res

    def fail(reason: str, email: str | None = None) -> RedirectResponse:
        auth_events.record(db, "login_failed", reason=reason, email=email, ip=key, user_agent=agent)
        return go(f"{app_url}/login?error={reason}")

    # counted like a passphrase attempt, so failures cannot flood the audit log (ASSUMED 63)
    if not limiter.attempt(key):
        return go(f"{app_url}/login?error=too_many")
    if error:
        return fail("cancelled")
    if not code or not flow_state or not state or not secrets.compare_digest(state, flow_state):
        return fail("state")
    transport = getattr(request.app.state, "google_transport", None)
    try:
        id_token = google.exchange_code(settings, code, verifier, transport=transport)
    except google.GoogleError:
        return fail("exchange")
    try:
        claims = google.check_claims(id_token, settings, nonce)
    except google.GoogleError:
        return fail("token")

    # The user row first, then its audit rows; the handoff code only after both (ASSUMED 61).
    row = users.get_by_google_sub(db, claims["sub"])
    if row is None:
        row = users.create_google(
            db, sub=claims["sub"], email=claims["email"], display_name=claims.get("name") or ""
        )
        auth_events.record(
            db, "signup", user_id=row["id"], email=claims["email"], ip=key, user_agent=agent
        )
    elif row.get("email") != claims["email"]:
        users.update_google_profile(db, row["id"], email=claims["email"])
    auth_events.record(
        db, "login", user_id=row["id"], email=claims["email"], ip=key, user_agent=agent
    )
    limiter.forgive(key)
    handoff = request.app.state.google_handoff.issue(row["id"])
    # in the fragment: never sent to a server, so it stays out of logs and Referer headers
    return go(f"{app_url}/login#google={handoff}")


@router.post("/exchange", response_model=LoginResponse)
def google_exchange(
    body: ExchangeIn, request: Request, settings: GoogleSettings, db: DbDep
) -> LoginResponse:
    """Trade the one-time code from the callback for a session."""
    user_id = request.app.state.google_handoff.take(body.code)
    row = users.get_by_id(db, user_id) if user_id else None
    if row is None:
        raise unauthorized("invalid_code", "That sign-in has expired. Please sign in again.")
    return session_for(row, settings)
