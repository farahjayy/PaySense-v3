"""Shared request field types. Money crosses the API as integer sen only (ADR D-29)."""

from typing import Annotated

from pydantic import Field, StrictInt

MAX_SEN = 100_000_000_000  # RM 1 billion: far above any real amount, far below integer overflow

# A strict positive integer: 100.5, "100" and true are all rejected with a validation error, so a
# float or a string can never become money.
Sen = Annotated[
    StrictInt,
    Field(gt=0, le=MAX_SEN, description="Money in integer sen (100 sen = RM 1)"),
]
