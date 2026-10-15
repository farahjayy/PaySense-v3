"""Merchant-text matching shared by recurring detection, the forecast and the repositories."""

import re

NON_LETTERS = re.compile(r"[^a-z ]+")
SPACES = re.compile(r"\s+")

# Students write the month into the description ("Rent july", "June PESP Allowance"). A month is
# when a payment happened, not who it went to, so it must not make each month a different item
# (ADR D-44). Whole words only: "maybank" and "mayflower" are untouched. Short forms that are
# also given names (jan, jun, mar, dec) are kept, so "Transfer to Jun" and "Transfer to Jan" stay
# two payees.
MONTH_WORDS = frozenset(
    {
        # English, in full
        "january", "february", "march", "april", "may", "june", "july", "august",
        "september", "october", "november", "december",
        # English short forms that are not also a common name or word
        "feb", "apr", "jul", "aug", "sep", "sept", "oct", "nov",
        # Malay, in full. "Mac" and "Mei" are left out: they are also an Apple product and a name.
        "januari", "februari", "julai", "ogos", "oktober", "disember",
    }
)  # fmt: skip


def normalise_merchant(text: str | None) -> str:
    """Lower-case letters only: digits, references, punctuation and month names are dropped."""
    if not text:
        return ""
    words = SPACES.sub(" ", NON_LETTERS.sub(" ", text.lower())).split()
    return " ".join(word for word in words if word not in MONTH_WORDS)
