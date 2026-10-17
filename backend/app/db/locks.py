"""Per-user database locks (ADR D-49): a row in `user_locks` keyed by (user_id, name).

Taking a lock is an insert, so the primary key makes it atomic across server processes: a second
worker's insert fails and it answers 409 instead of racing the first. A lock older than
STALE_AFTER_SECONDS is treated as abandoned (a crash between acquire and release) and taken over.
"""

import datetime as dt
from collections.abc import Iterator
from contextlib import contextmanager

from postgrest import APIError

from app.db.base import require_user_id
from app.db.client import Database

TABLE = "user_locks"
NAMES = frozenset({"plan_create", "assistant_chat"})
STALE_AFTER_SECONDS = 120
UNIQUE_VIOLATION = "23505"


def _check(name: str) -> None:
    if name not in NAMES:
        raise ValueError(f"unknown lock {name!r}")


def acquire(db: Database, user_id: str, name: str, *, now: dt.datetime | None = None) -> str | None:
    """The holder's stamp if this caller now holds the lock (pass it to `release`); None if
    someone else holds a fresh one."""
    uid = require_user_id(user_id)
    _check(name)
    stamp = (now or dt.datetime.now(dt.UTC)).isoformat()
    try:
        db.table(TABLE).insert({"user_id": uid, "name": name, "acquired_at": stamp}).execute()
        return stamp
    except APIError as err:
        if err.code != UNIQUE_VIOLATION:
            raise
    cutoff = (dt.datetime.now(dt.UTC) - dt.timedelta(seconds=STALE_AFTER_SECONDS)).isoformat()
    # take over an abandoned lock: only a delete that still finds the old row wins the race
    stale = (
        (db.table(TABLE).delete().eq("user_id", uid).eq("name", name).lt("acquired_at", cutoff))
        .execute()
        .data
    )
    if not stale:
        return None
    try:
        db.table(TABLE).insert({"user_id": uid, "name": name, "acquired_at": stamp}).execute()
        return stamp
    except APIError as err:
        if err.code != UNIQUE_VIOLATION:
            raise
        return None


def release(db: Database, user_id: str, name: str, stamp: str | None = None) -> None:
    """Free the lock. With the holder's stamp, only that holder's lock: a slow request whose lock
    was taken over as stale must not free the new holder's."""
    uid = require_user_id(user_id)
    _check(name)
    query = db.table(TABLE).delete().eq("user_id", uid).eq("name", name)
    if stamp is not None:
        query = query.eq("acquired_at", stamp)
    query.execute()


@contextmanager
def held(db: Database, user_id: str, name: str) -> Iterator[bool]:
    """Yield whether the lock was taken; release it afterwards only if it was."""
    stamp = acquire(db, user_id, name)
    try:
        yield stamp is not None
    finally:
        if stamp is not None:
            release(db, user_id, name, stamp)
