"""Tester account seeding. There is deliberately no sign-up endpoint (supervisor decision, D-03)."""

from typing import Any

from app.db import user_settings, users
from app.db.client import Database


def seed_user(
    db: Database, *, username: str, display_name: str, persona: str | None
) -> tuple[dict[str, Any], bool]:
    """Create the user and its settings row if missing. Returns (user, created). Idempotent."""
    if persona is not None and persona not in users.PERSONAS:
        raise ValueError(f"persona must be one of {sorted(users.PERSONAS)}")
    existing = users.get_by_username(db, username)
    created = existing is None
    try:
        user = existing or users.create(
            db, username=username, display_name=display_name, persona=persona
        )
    except users.UsernameTakenError:
        user, created = users.get_by_username(db, username), False
    user_settings.create_default(db, user["id"])
    return user, created
