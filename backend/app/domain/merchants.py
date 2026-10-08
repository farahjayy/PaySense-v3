"""Merchant-text matching shared by recurring detection, the forecast and the repositories."""

import re

NON_LETTERS = re.compile(r"[^a-z ]+")
SPACES = re.compile(r"\s+")


def normalise_merchant(text: str | None) -> str:
    """Lower-case letters only: digits, references, dates and punctuation are dropped."""
    if not text:
        return ""
    return SPACES.sub(" ", NON_LETTERS.sub(" ", text.lower())).strip()
