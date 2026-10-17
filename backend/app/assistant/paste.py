"""Import by chat (WP4d): rows the model read from pasted text, checked against that text.

The model is good at reading messy lines and bad at being trusted with numbers, so every row it
submits is grounded: its amount and its date must be written in the pasted text (the server's own
copy of this turn's message, never the model's arguments). A row that is not grounded is rejected
with a reason; a description is kept only if it appears in the paste. Then the rows go through
the same validation, categoriser and duplicate flags as a file import, and a pending
`confirm_import` action is stored for the person to confirm (ADR D-48).
"""

import re
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.imports import ConfirmRow
from app.assistant.numbers import NUMBER, normalise
from app.domain.categorize import guess_category
from app.domain.csv_import import CsvImportError, fingerprint, flag_duplicates, parse_csv

MAX_ROWS = 50
MAX_PASTE_CHARS = 8000
MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january", "januari"),
            ("feb", "february", "februari"),
            ("mar", "march", "mac"),
            ("apr", "april"),
            ("may", "mei"),
            ("jun", "june", "jun"),
            ("jul", "july", "julai"),
            ("aug", "august", "ogos", "ogo"),
            ("sep", "sept", "september"),
            ("oct", "october", "okt", "oktober"),
            ("nov", "november"),
            ("dec", "december", "dis", "disember"),
        ],
        start=1,
    )
    for name in names
}
_NUMERIC_DATE = re.compile(r"(?<!\d)(\d{1,2})[/.\-](\d{1,2})(?:[/.\-](\d{2}|\d{4}))?(?!\d)")
_ISO_DATE = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_DAY_MONTH = re.compile(
    r"(?<!\d)(\d{1,2})(?!\d)(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?(?:\s+(\d{4})(?!\d))?"
)
_MONTH_DAY = re.compile(
    r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(\d{4})(?!\d))?"
)


class PastedRowIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: date
    amount_sen: int = Field(gt=0, description="Integer sen exactly as written: RM15.50 is 1550")
    type: Literal["income", "expense", "savings"]
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=200)


class PasteArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rows: Annotated[list[PastedRowIn], Field(max_length=MAX_ROWS)] = Field(
        default_factory=list,
        description="The rows you read from the pasted text, one per transaction (at most 50). "
        "Leave empty to let the server read a well-formed statement itself.",
    )


@dataclass(frozen=True)
class Rejected:
    index: int
    reason: str


def _year(raw: str | None) -> int | None:
    if raw is None:
        return None
    value = int(raw)
    return value + 2000 if value < 100 else value


def dates_in(text: str) -> set[tuple[int, int, int | None]]:
    """(day, month, year or None) for every date written in the text (day before month, the
    Malaysian convention; ASSUMED 30)."""
    found: set[tuple[int, int, int | None]] = set()
    for y, m, d in _ISO_DATE.findall(text):
        found.add((int(d), int(m), int(y)))
    for d, m, y in _NUMERIC_DATE.findall(text):
        found.add((int(d), int(m), _year(y or None)))
    for d, name, y in _DAY_MONTH.findall(text):
        if name.lower() in MONTHS:
            found.add((int(d), MONTHS[name.lower()], _year(y or None)))
    for name, d, y in _MONTH_DAY.findall(text):
        if name.lower() in MONTHS:
            found.add((int(d), MONTHS[name.lower()], _year(y or None)))
    return {(d, m, y) for d, m, y in found if 1 <= d <= 31 and 1 <= m <= 12}


def amounts_in(text: str) -> set[str]:
    return {normalise(token) for token in NUMBER.findall(text)}


def _amount_grounded(amount_sen: int, amounts: set[str]) -> bool:
    ringgit = f"{amount_sen // 100}.{amount_sen % 100:02d}"
    return normalise(ringgit) in amounts


def _date_grounded(day: date, dates: set[tuple[int, int, int | None]]) -> bool:
    return any(
        d == day.day and m == day.month and (y is None or y == day.year) for d, m, y in dates
    )


def _squash(text: str) -> str:
    return " ".join(text.casefold().split())


def ground_rows(
    rows: list[PastedRowIn], pasted: str
) -> tuple[list[dict[str, Any]], list[Rejected]]:
    """Keep the rows whose amount and date are written in the paste; say why the others went."""
    amounts, dates, haystack = amounts_in(pasted), dates_in(pasted), _squash(pasted)
    kept: list[dict[str, Any]] = []
    rejected: list[Rejected] = []
    for index, row in enumerate(rows):
        if not _amount_grounded(row.amount_sen, amounts):
            ringgit = f"{row.amount_sen // 100}.{row.amount_sen % 100:02d}"
            rejected.append(Rejected(index, f"RM {ringgit} is not written in the pasted text."))
            continue
        if not _date_grounded(row.date, dates):
            rejected.append(Rejected(index, f"{row.date.isoformat()} is not in the pasted text."))
            continue
        description = row.description
        if description and _squash(description) not in haystack:
            description = None  # the model's own words are not the person's data
        category = row.category or guess_category(description)
        try:
            clean = ConfirmRow.model_validate(
                {"date": row.date, "amount_sen": row.amount_sen, "type": row.type,
                 "category": category or "Other", "description": description}
            )  # fmt: skip
        except ValidationError as err:
            rejected.append(Rejected(index, f"Not a valid row ({err.errors()[0]['msg']})."))
            continue
        kept.append(clean.model_dump(mode="json"))
    return kept, rejected


def parse_deterministically(pasted: str) -> tuple[list[dict[str, Any]], list[Rejected]]:
    """The importer's own parser, for a paste that is already a statement (guided mode)."""
    try:
        preview = parse_csv(pasted)
    except CsvImportError as err:
        return [], [Rejected(0, err.message)]
    rows = [
        ConfirmRow.model_validate(
            {
                "date": r.date,
                "amount_sen": r.amount_sen,
                "type": r.type,
                "category": r.category_guess,
                "description": r.description,
            }
        ).model_dump(mode="json")  # fmt: skip
        for r in preview.rows
    ]
    return rows[:MAX_ROWS], [Rejected(s.row, s.reason) for s in preview.skipped]


def with_duplicates(
    rows: list[dict[str, Any]], stored_fingerprints: list[str]
) -> list[tuple[dict[str, Any], bool]]:
    """Each row with whether the ledger already holds it (multiplicity-aware, like a file)."""
    from app.domain.csv_import import ImportRow

    staged = [
        ImportRow(
            row=i,
            date=date.fromisoformat(r["date"]),
            amount_sen=r["amount_sen"],
            type=r["type"],
            category_guess=r["category"],
            description=r.get("description"),
            issues=(),
            fingerprint=fingerprint(
                date.fromisoformat(r["date"]), r["amount_sen"], r["type"], r.get("description")
            ),
        )  # fmt: skip
        for i, r in enumerate(rows)
    ]
    flagged = flag_duplicates(staged, stored_fingerprints)
    return [(rows[f.row], f.duplicate) for f in flagged]
