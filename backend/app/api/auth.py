import ipaddress
from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.api.deps import CurrentUser, DbDep, SettingsDep, get_login_limiter
from app.api.rate_limit import LoginRateLimiter
from app.api.schemas import ERROR_RESPONSES, LoginRequest, LoginResponse, UserOut
from app.core.errors import api_error, unauthorized
from app.core.security import create_access_token
from app.db import users

router = APIRouter(prefix="/auth", tags=["auth"], responses=ERROR_RESPONSES)

LimiterDep = Annotated[LoginRateLimiter, Depends(get_login_limiter)]


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


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest, request: Request, db: DbDep, settings: SettingsDep, limiter: LimiterDep
) -> LoginResponse:
    key = client_key(request)
    if limiter.is_blocked(key):
        raise api_error(
            429,
            "too_many_attempts",
            "Too many failed logins. Try again in a few minutes.",
            headers={"Retry-After": str(int(limiter.window_seconds))},
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
