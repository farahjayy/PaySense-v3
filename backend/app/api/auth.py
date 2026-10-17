import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.deps import (
    CurrentUser,
    DbDep,
    SettingsDep,
    get_login_limiter,
    get_username_limiter,
)
from app.api.rate_limit import LoginRateLimiter
from app.api.schemas import ERROR_RESPONSES, LoginRequest, LoginResponse, UserOut
from app.core.errors import api_error, unauthorized
from app.core.passphrase import verify_passphrase
from app.core.security import create_access_token
from app.db import users

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)

LimiterDep = Annotated[LoginRateLimiter, Depends(get_login_limiter)]
UsernameLimiterDep = Annotated[LoginRateLimiter, Depends(get_username_limiter)]
# One answer for every failure (unknown user, wrong passphrase, no passphrase set), so the login
# form cannot be used to find out which usernames exist (ADR D-49).
_INVALID = ("invalid_credentials", "That username and passphrase do not match.")


def client_key(request: Request) -> str:
    """Rate-limit bucket: the peer address, with IPv6 collapsed to its /64.

    Forwarded headers are only honoured by uvicorn itself, and only from the addresses given to
    --forwarded-allow-ips; this function deliberately never reads X-Forwarded-For.
    """
    host = request.client.host if request.client else "unknown"
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return host


def _too_many(limiter: LoginRateLimiter):
    return api_error(
        429,
        "too_many_attempts",
        "Too many failed logins. Try again in a few minutes.",
        headers={"Retry-After": str(int(limiter.window_seconds))},
    )


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    username_limiter: UsernameLimiterDep,
) -> LoginResponse:
    key = client_key(request)
    name_key = f"user:{body.username.strip().lower()}"
    if limiter.is_blocked(key):
        raise _too_many(limiter)
    if username_limiter.is_blocked(name_key):
        raise _too_many(username_limiter)
    row = users.get_by_username(db, body.username)
    # verify even when there is no such user: the time taken must not say whether it exists
    matched = verify_passphrase(row.get("passphrase_hash") if row else None, body.passphrase)
    if row is None or not matched:
        limiter.record_failure(key)
        username_limiter.record_failure(name_key)
        raise unauthorized(*_INVALID)
    token, _ = create_access_token(row["id"], settings, version=int(row.get("token_version") or 0))
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


@router.post("/logout", status_code=204)
def logout(user: CurrentUser, db: DbDep) -> Response:
    """End every session of this user: their token version moves on, so older tokens fail."""
    users.bump_token_version(db, user.id)
    return Response(status_code=204)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return user
