"""The second login factor (ADR D-49): a passphrase stored as an scrypt hash with a per-user salt.

Stored form: `scrypt$<n>$<r>$<p>$<salt, base64>$<hash, base64>`, so the cost parameters travel
with the hash and can be raised later without breaking existing passphrases. Comparison is
constant time, and checking a user who has no passphrase (or does not exist) still runs scrypt
once, so response time does not reveal which usernames exist.
"""

import base64
import hashlib
import hmac
import secrets

SCHEME = "scrypt"
N, R, P = 2**14, 8, 1  # ASSUMED (D-49): ~16 MB and ~50 ms per check
SALT_BYTES = 16
KEY_BYTES = 32
MIN_LENGTH = 12
MAX_LENGTH = 128
_DUMMY_SALT = b"paysense-no-user"


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _derive(passphrase: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=64 * 1024 * 1024,
        dklen=KEY_BYTES,
    )


def _check_strength(passphrase: str) -> None:
    if not isinstance(passphrase, str) or len(passphrase.strip()) < MIN_LENGTH:
        raise ValueError(f"a passphrase needs at least {MIN_LENGTH} characters")
    if len(passphrase) > MAX_LENGTH:
        raise ValueError(f"a passphrase can be at most {MAX_LENGTH} characters")


def hash_passphrase(passphrase: str) -> str:
    _check_strength(passphrase)
    salt = secrets.token_bytes(SALT_BYTES)
    digest = _derive(passphrase, salt, N, R, P)
    return f"{SCHEME}${N}${R}${P}${_b64(salt)}${_b64(digest)}"


def verify_passphrase(stored: str | None, candidate: str) -> bool:
    """True only when `candidate` matches `stored`. Never raises on a malformed stored value."""
    parts = stored.split("$") if isinstance(stored, str) else []
    try:
        scheme, n, r, p, salt, digest = parts
        if scheme != SCHEME:
            raise ValueError
        params = (int(n), int(r), int(p))
        expected = base64.b64decode(digest, validate=True)
        salt_bytes = base64.b64decode(salt, validate=True)
    except ValueError:
        _derive(candidate or "", _DUMMY_SALT, N, R, P)  # same cost as a real check
        return False
    actual = _derive(candidate or "", salt_bytes, *params)
    return hmac.compare_digest(actual, expected)


def generate_passphrase() -> str:
    """A random passphrase for a seeded account (delivered privately, never committed)."""
    return secrets.token_urlsafe(18)
