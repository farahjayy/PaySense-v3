"""Permission tiers (ADR D-48).

    0 Read      reads the signed-in user's data, changes nothing
    1 Propose   computes or parses, or stores a *pending* action; never changes the ledger
    2 Write     changes data: only the confirm endpoint runs these, after the person presses
                Confirm on a card built from the validated payload. Never the model.

The tool executor serves the model and guided mode, and both stop at Tier 1. Writes are not in the
model's registry at all (`writes.py`); this check is the second wall, so a write registered in
the wrong place by mistake still cannot run.
"""

from typing import Literal

Caller = Literal["model", "guided"]
_MAX_TIER: dict[str, int] = {"model": 1, "guided": 1}
FORBIDDEN_KEYS = frozenset({"user_id", "userid", "user", "uid", "owner_id"})


def max_tier(caller: str) -> int:
    if caller not in _MAX_TIER:
        raise ValueError(f"unknown caller {caller!r}: writes run only from the confirm endpoint")
    return _MAX_TIER[caller]


def allowed(tier: int, caller: str) -> bool:
    return tier <= max_tier(caller)


def names_a_user(value: object) -> bool:
    """True if any key, at any depth, tries to say whose data this is."""
    if isinstance(value, dict):
        return any(
            (isinstance(k, str) and k.replace("-", "_").casefold() in FORBIDDEN_KEYS)
            or names_a_user(v)
            for k, v in value.items()
        )
    if isinstance(value, list | tuple):
        return any(names_a_user(v) for v in value)
    return False
