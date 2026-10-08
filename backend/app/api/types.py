"""Shared request field types. Money crosses the API as integer sen only (ADR D-29).

Everything here exists so that ordinary-but-awkward input (blank text, a NUL character, an absurd
date, an explicit null) is refused with a clean 422 *at the edge* instead of reaching a repository
or the database and surfacing as a 500.
"""

import datetime as dt
from collections.abc import Iterable
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, StrictInt, StringConstraints

from app.domain.money import MAX_AMOUNT_SEN

MAX_SEN = MAX_AMOUNT_SEN
MIN_DATE = dt.date(2000, 1, 1)
MAX_DATE = dt.date(2100, 12, 31)

# A strict positive integer: 100.5, "100" and true are all rejected with a validation error, so a
# float or a string can never become money.
Sen = Annotated[
    StrictInt,
    Field(gt=0, le=MAX_SEN, description="Money in integer sen (100 sen = RM 1)"),
]

AppDate = Annotated[dt.date, Field(ge=MIN_DATE, le=MAX_DATE)]


def _no_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("must not contain NUL characters")
    return value


def text(max_length: int, *, required: bool = True):
    """A trimmed string without NUL characters. `required=False` also allows blank (stored as
    nothing by the repositories)."""
    return Annotated[
        str,
        StringConstraints(
            strip_whitespace=True, min_length=1 if required else 0, max_length=max_length
        ),
        AfterValidator(_no_nul),
    ]


def reject_explicit_nulls(model: BaseModel, fields: Iterable[str]) -> None:
    """For PATCH bodies: a field that was sent as null but cannot be null is a validation error
    (rather than a repository exception or, worse, a silent change)."""
    sent_null = [f for f in fields if f in model.model_fields_set and getattr(model, f) is None]
    if sent_null:
        raise ValueError(f"{', '.join(sent_null)} cannot be null")
