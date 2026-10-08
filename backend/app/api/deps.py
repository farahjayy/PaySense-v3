"""Shared FastAPI dependencies. Auth and database access live here, never in handlers."""

from datetime import UTC, date, datetime
from threading import Lock
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.rate_limit import LoginRateLimiter
from app.api.schemas import UserOut
from app.core.errors import unauthorized
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
        user_id = decode_access_token(credentials.credentials, settings)
    except InvalidTokenError as err:
        raise unauthorized("invalid_token", "Your session is invalid or has expired.") from err
    row = users.get_by_id(db, user_id)
    if row is None:
        raise unauthorized("invalid_token", "Your session is invalid or has expired.")
    return UserOut(
        id=row["id"],
        username=row["username"],
        display_name=row["display_name"],
        persona=row.get("persona"),
    )


CurrentUser = Annotated[UserOut, Depends(current_user)]
