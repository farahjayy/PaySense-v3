"""The categories a person can pick, and the rules for managing their own (ADR D-43).

Twelve are built in and locked: the importer guesses from them, and the engines key off `Refund`
and `Transfer` (and the BNPL category plans assign), so none of them can be renamed or deleted.
Any other category is the person's own: added by hand, or typed in their own spreadsheet and
imported as written (D-42), in which case it exists only on transactions until they manage it.
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from app.domain.categorize import BNPL, REFUND, TRANSFER

BUILT_IN = (
    "Food",
    "Transport",
    "Rent",
    "Salary",
    "Allowance",
    "Shopping",
    "Bills",
    "Entertainment",
    "Education",
    REFUND,
    TRANSFER,
    "Other",
)
APP_ASSIGNED = (BNPL,)  # logged by a BNPL plan; never chosen by hand
LOCKED = BUILT_IN + APP_ASSIGNED
MAX_NAME_LENGTH = 40

NOTES = {
    REFUND: "Money back for a purchase. It is taken off your spending, not counted as income.",
    TRANSFER: "A move between your own accounts. It is left out of income and spending.",
    BNPL: "Added by your BNPL plans when an instalment is paid. You cannot pick it by hand.",
}

_SPACES = re.compile(r"\s+")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_LOCKED_BY_FOLDED = {name.casefold(): name for name in LOCKED}


def clean_name(raw: object) -> str:
    """The name as it will be stored; ValueError (with a sentence for the person) if unusable."""
    if not isinstance(raw, str):
        raise ValueError("Give the category a name.")
    if _CONTROL.search(raw):
        raise ValueError("A category name cannot contain line breaks or control characters.")
    name = _SPACES.sub(" ", raw).strip()
    if not any(ch.isalpha() for ch in name):
        raise ValueError("A category name needs at least one letter.")
    if len(name) > MAX_NAME_LENGTH:
        raise ValueError(f"A category name can be at most {MAX_NAME_LENGTH} characters.")
    return name


def locked_name(name: str) -> str | None:
    """The built-in name this matches, whatever its case, or None if it is the person's own."""
    return _LOCKED_BY_FOLDED.get(_SPACES.sub(" ", name).strip().casefold())


@dataclass(frozen=True)
class CategoryEntry:
    name: str
    builtin: bool  # one of the app's own
    locked: bool  # cannot be renamed or deleted
    assignable: bool  # can be chosen on a transaction
    note: str | None
    transaction_count: int


def build_listing(custom_names: Iterable[str], counts: Mapping[str, int]) -> list[CategoryEntry]:
    """Built-in categories first, then the person's own: those added by hand and every other
    category their transactions carry, once each and in alphabetical order."""
    own = {name for name in custom_names} | {name for name in counts if name not in LOCKED}
    entries = [
        CategoryEntry(
            name=name,
            builtin=True,
            locked=True,
            assignable=name not in APP_ASSIGNED,
            note=NOTES.get(name),
            transaction_count=counts.get(name, 0),
        )
        for name in LOCKED
    ]
    entries.extend(
        CategoryEntry(
            name=name,
            builtin=False,
            locked=False,
            assignable=True,
            note=None,
            transaction_count=counts.get(name, 0),
        )
        for name in sorted(own, key=lambda n: (n.casefold(), n))
    )
    return entries
