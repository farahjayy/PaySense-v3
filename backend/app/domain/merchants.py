"""Merchant-text matching shared by recurring detection, the forecast and the repositories."""

import re

NON_LETTERS = re.compile(r"[^a-z ]+")
SPACES = re.compile(r"\s+")

# Students write the month into the description ("Rent july", "June PESP Allowance"). A month is
# when a payment happened, not who it went to, so it must not make each month a different item
# (ADR D-44). Whole words only: "maybank" and "mayflower" are untouched.
MONTH_WORDS = frozenset(
    {
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
    }
)  # fmt: skip


def normalise_merchant(text: str | None) -> str:
    """Lower-case letters only: digits, references, punctuation and month names are dropped."""
    if not text:
        return ""
    words = SPACES.sub(" ", NON_LETTERS.sub(" ", text.lower())).split()
    return " ".join(word for word in words if word not in MONTH_WORDS)
