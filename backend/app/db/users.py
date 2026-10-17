"""Users. `get_by_username` is the one deliberately unscoped read: it is how a session starts."""

import re
from typing import Any

from postgrest import APIError

from app.core.passphrase import hash_passphrase
from app.db.base import is_uuid, require_user_id
from app.db.client import Database

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
PERSONAS = frozenset({"frequent_bnpl", "budget_conscious", "irregular_income"})
UNIQUE_VIOLATION = "23505"


class UsernameTakenError(Exception):
    """A user with this username (case-insensitive) already exists."""


def normalise_username(raw: str) -> str | None:
    """Trimmed username if it is well-formed, else None. Never raises on hostile input."""
    candidate = raw.strip() if isinstance(raw, str) else ""
    return candidate if USERNAME_PATTERN.fullmatch(candidate) else None


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
    if not is_uuid(user_id):
        return None
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


def set_passphrase(db: Database, user_id: str, passphrase: str) -> None:
    """Store the scrypt hash of a new passphrase (ADR D-49). Ends every existing session, since
    whoever held the old passphrase may hold a token too."""
    uid = require_user_id(user_id)
    stored = hash_passphrase(passphrase)
    user = get_by_id(db, uid)
    if user is None:
        raise ValueError("no such user")
    version = int(user.get("token_version") or 0) + 1
    db.table("users").update({"passphrase_hash": stored, "token_version": version}).eq(
        "id", uid
    ).execute()


def bump_token_version(db: Database, user_id: str) -> int:
    """Log the user out everywhere: every token carrying an older version is refused."""
    uid = require_user_id(user_id)
    user = get_by_id(db, uid)
    if user is None:
        raise ValueError("no such user")
    version = int(user.get("token_version") or 0) + 1
    db.table("users").update({"token_version": version}).eq("id", uid).execute()
    return version
