"""Users. `get_by_username` is the one deliberately unscoped read: it is how a session starts."""

import re
from typing import Any

from postgrest import APIError

from app.db.client import Database

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
PERSONAS = frozenset({"frequent_bnpl", "budget_conscious", "irregular_income"})
UNIQUE_VIOLATION = "23505"


class UsernameTakenError(Exception):
    """A user with this username (case-insensitive) already exists."""


def normalise_username(raw: str) -> str | None:
    """Trimmed username if it is well-formed, else None. Never raises on hostile input."""
    candidate = raw.strip() if isinstance(raw, str) else ""
    return candidate if USERNAME_PATTERN.match(candidate) else None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def get_by_username(db: Database, username: str) -> dict[str, Any] | None:
    name = normalise_username(username)
    if name is None:
        return None
    rows = (
        db.table("users").select("*").ilike("username", _escape_like(name)).limit(2).execute().data
    )
    exact = [r for r in rows if r["username"].lower() == name.lower()]
    return exact[0] if exact else None


def get_by_id(db: Database, user_id: str) -> dict[str, Any] | None:
    rows = db.table("users").select("*").eq("id", user_id).limit(1).execute().data
    return rows[0] if rows else None


def create(
    db: Database, *, username: str, display_name: str, persona: str | None = None
) -> dict[str, Any]:
    name = normalise_username(username)
    if name is None:
        raise ValueError("username must be 1-64 characters: letters, digits, '.', '_' or '-'")
    if persona is not None and persona not in PERSONAS:
        raise ValueError(f"persona must be one of {sorted(PERSONAS)}")
    if not display_name.strip():
        raise ValueError("display_name is required")
    try:
        created = (
            db.table("users")
            .insert({"username": name, "display_name": display_name.strip(), "persona": persona})
            .execute()
            .data
        )
    except APIError as err:
        if err.code == UNIQUE_VIOLATION:
            raise UsernameTakenError(name) from err
        raise
    return created[0]
