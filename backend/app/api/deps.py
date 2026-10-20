"""Shared FastAPI dependencies. Auth and database access live here, never in handlers."""

from datetime import UTC, date, datetime
from threading import Lock
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.rate_limit import DailyQuota, LoginRateLimiter, RequestRateLimiter
from app.api.schemas import UserOut
from app.core.errors import api_error, unauthorized
from app.core.security import InvalidTokenError, decode_access_token
from app.core.settings import Settings
from app.db import users
from app.db.client import Database, build_client

_bearer = HTTPBearer(auto_error=False)
_db_lock = Lock()


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_db(request: Request) -> Database:
    """The app's database, built on first use so tests and `--help` never need credentials."""
    state = request.app.state
    if state.db is None:
        with _db_lock:
            if state.db is None:
                state.db = build_client(state.settings)
    return state.db


def get_login_limiter(request: Request) -> LoginRateLimiter:
    return request.app.state.login_limiter


def get_username_limiter(request: Request) -> LoginRateLimiter:
    return request.app.state.username_limiter


MALAYSIA = ZoneInfo("Asia/Kuala_Lumpur")


def malaysia_today(now: datetime | None = None) -> date:
    """Today's date in Malaysia. The server runs in UTC, which is yesterday for the first eight
    hours of every Malaysian day, so "today" must never come from the server clock directly."""
    return (now or datetime.now(UTC)).astimezone(MALAYSIA).date()


def get_today() -> date:
    """A dependency so tests can pin the clock with `dependency_overrides`."""
    return malaysia_today()


TodayDep = Annotated[date, Depends(get_today)]
SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
DbDep = Annotated[Database, Depends(get_db)]


def current_user(
    settings: SettingsDep,
    db: DbDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> UserOut:
    if credentials is None:
        raise unauthorized("not_authenticated", "Log in to continue.")
    try:
        user_id, version = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError as err:
        raise unauthorized("invalid_token", "Your session is invalid or has expired.") from err
    row = users.get_by_id(db, user_id)
    # a token issued before the last logout (or passphrase change) carries an older version
    if row is None or int(row.get("token_version") or 0) != version:
        raise unauthorized("invalid_token", "Your session is invalid or has expired.")
    return UserOut(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        persona=row.get("persona"),
        email=row.get("email"),
    )


CurrentUser = Annotated[UserOut, Depends(current_user)]


def get_request_limiter(request: Request) -> RequestRateLimiter:
    return request.app.state.request_limiter


def rate_limited(bucket: str, max_requests: int, window_seconds: float):
    """A route dependency: at most `max_requests` per user per window on this bucket."""

    def check(
        user: CurrentUser,
        limiter: Annotated[RequestRateLimiter, Depends(get_request_limiter)],
    ) -> None:
        allowed, wait = limiter.allow(f"{bucket}:{user.id}", max_requests, window_seconds)
        if not allowed:
            raise api_error(
                429,
                "too_many_requests",
                f"You are doing that too quickly. Try again in {wait} seconds.",
                headers={"Retry-After": str(wait)},
            )

    return Depends(check)


def get_write_quota(request: Request) -> DailyQuota:
    return request.app.state.write_quota


def seconds_to_malaysian_midnight(now: datetime | None = None) -> int:
    local = (now or datetime.now(UTC)).astimezone(MALAYSIA)
    midnight = datetime.combine(local.date(), datetime.min.time(), MALAYSIA)
    return max(1, int(86400 - (local - midnight).total_seconds()))


def check_write_quota(
    user: CurrentUser,
    settings: SettingsDep,
    quota: Annotated[DailyQuota, Depends(get_write_quota)],
) -> None:
    """Every route that changes a user's data counts one write against their daily quota."""
    if not quota.use(user.id, malaysia_today().isoformat(), settings.daily_write_quota):
        wait = seconds_to_malaysian_midnight()
        raise api_error(
            429,
            "daily_write_quota",
            "You have made as many changes as one day allows. Try again tomorrow.",
            headers={"Retry-After": str(wait)},
        )


WRITE_QUOTA = Depends(check_write_quota)


def check_assistant_quota(
    user: CurrentUser,
    settings: SettingsDep,
    quota: Annotated[DailyQuota, Depends(get_write_quota)],
) -> None:
    """Each assistant chat or guided call writes audit rows (and may store a proposal), so the
    assistant has its own daily cap, counted apart from the user's data writes."""
    day = malaysia_today().isoformat()
    if not quota.use(f"assistant:{user.id}", day, settings.assistant_daily_requests):
        raise api_error(
            429,
            "assistant_daily_quota",
            "You have asked the assistant as much as one day allows. Try again tomorrow; the "
            "screens still work.",
            headers={"Retry-After": str(seconds_to_malaysian_midnight())},
        )


ASSISTANT_QUOTA = Depends(check_assistant_quota)
