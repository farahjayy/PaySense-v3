from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import CurrentUser, DbDep, SettingsDep, get_login_limiter
from app.api.rate_limit import LoginRateLimiter
from app.api.schemas import LoginRequest, LoginResponse, UserOut
from app.core.errors import api_error, unauthorized
from app.core.security import create_access_token
from app.db import users

router = APIRouter(prefix="/auth", tags=["auth"])

LimiterDep = Annotated[LoginRateLimiter, Depends(get_login_limiter)]


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest, request: Request, db: DbDep, settings: SettingsDep, limiter: LimiterDep
) -> LoginResponse:
    key = _client_key(request)
    if limiter.is_blocked(key):
        raise api_error(
            429, "too_many_attempts", "Too many failed logins. Try again in a few minutes."
        )
    row = users.get_by_username(db, body.username)
    if row is None:
        limiter.record_failure(key)
        raise unauthorized("unknown_username", "No account with that username.")
    token, _ = create_access_token(row["id"], settings)
    return LoginResponse(
        access_token=token,
        expires_in=settings.session_ttl_hours * 3600,
        user=UserOut(
            id=row["id"],
            username=row["username"],
            display_name=row["display_name"],
            persona=row.get("persona"),
        ),
    )


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return user
