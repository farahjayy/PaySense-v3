"""The categories a person adds themselves (ADR D-43). Every function takes `user_id` first and goes
through ScopedTable. The built-in categories are code, not rows (app/domain/categories.py)."""

from typing import Any

from postgrest import APIError

from app.db.base import ScopedTable
from app.db.client import Database
from app.domain.categories import clean_name, locked_name

TABLE = "user_categories"
UNIQUE_VIOLATION = "23505"


class DuplicateCategory(ValueError):
    """The name is a built-in category, or one the person already has (in any case)."""


def _table(db: Database) -> ScopedTable:
    return ScopedTable(db, TABLE)


def _usable(name: object) -> str:
    cleaned = clean_name(name)
    if locked_name(cleaned) is not None:
        raise DuplicateCategory(f"{cleaned} is already a built-in category.")
    return cleaned


def names(db: Database, user_id: str) -> list[str]:
    rows = _table(db).list_rows(user_id, columns="name")
    return sorted((r["name"] for r in rows), key=lambda n: (n.casefold(), n))


def add(db: Database, user_id: str, name: str) -> dict[str, Any]:
    cleaned = _usable(name)
    try:
        return _table(db).insert(user_id, {"name": cleaned})
    except APIError as err:
        if err.code == UNIQUE_VIOLATION:
            raise DuplicateCategory(f"You already have a category called {cleaned}.") from err
        raise


def rename(db: Database, user_id: str, old: str, new: str) -> dict[str, Any] | None:
    """The renamed row, or None if the person never added a category called `old`. A change of
    case only (gym to Gym) is allowed; any other clash with their own categories is refused."""
    cleaned = _usable(new)
    rows = _table(db).list_rows(user_id, name=old)
    if not rows:
        return None
    try:
        return _table(db).update(user_id, rows[0]["id"], {"name": cleaned})
    except APIError as err:
        if err.code == UNIQUE_VIOLATION:
            raise DuplicateCategory(f"You already have a category called {cleaned}.") from err
        raise


def remove(db: Database, user_id: str, name: str) -> bool:
    rows = _table(db).list_rows(user_id, name=name)
    return bool(rows) and _table(db).delete(user_id, rows[0]["id"])
