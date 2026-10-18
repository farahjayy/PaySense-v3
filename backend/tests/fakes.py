"""Test helpers around the in-memory database (`app/db/memory.py`, moved there for the security
drill's sandbox, ADR D-58): seeded passphrases and consent for the fake users."""

from app.db.memory import (  # noqa: F401  (re-exported for the tests and scripts)
    FOREIGN_KEYS,
    HAS_CREATED_AT,
    NO_ID_TABLES,
    FakeSupabase,
    _now,
)

# Every test account's passphrase. Hashed once per run: scrypt is deliberately slow.
TEST_PASSPHRASE = "correct horse battery staple"
_TEST_HASH: list[str] = []


def give_test_passphrase(db: "FakeSupabase", username: str) -> None:
    """Set TEST_PASSPHRASE on a seeded fake user without paying for scrypt every time."""
    from app.core.passphrase import hash_passphrase

    if not _TEST_HASH:
        _TEST_HASH.append(hash_passphrase(TEST_PASSPHRASE))
    for row in db.rows("users"):
        if row["username"].lower() == username.lower():
            row["passphrase_hash"] = _TEST_HASH[0]


def accept_test_consent(db: "FakeSupabase", username: str) -> None:
    """Mark a seeded fake user as having accepted the current privacy notice (WP19)."""
    from app.domain.consent import CONSENT_VERSION

    user = next(u for u in db.rows("users") if u["username"].lower() == username.lower())
    for row in db.rows("user_settings"):
        if row["user_id"] == user["id"]:
            row["consent_version"] = CONSENT_VERSION
            row["consent_at"] = _now()
