"""Import by chat (WP4d): rows the model read from pasted text, checked against that text.

The model is good at reading messy lines and bad at being trusted with numbers, so every row it
submits is grounded: its amount and its date must be written on one line of the pasted text (the
server's own copy of this turn's message, never the model's arguments), each line grounding at
most one row. A row that is not grounded is rejected
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


Day = tuple[int, int, int | None]


@dataclass(frozen=True)
class Line:
    """One line of the paste: the dates and the amounts written on it. A number that is part of
    a date is never an amount, so a year, day or month cannot be read as money."""

    text: str
    dates: frozenset[Day]
    amounts: frozenset[str]


def _date_spans(text: str) -> list[tuple[Day, tuple[int, int]]]:
    found: list[tuple[Day, tuple[int, int]]] = []
    for m in _ISO_DATE.finditer(text):
        y, mo, d = m.groups()
        found.append(((int(d), int(mo), int(y)), m.span()))
    for m in _NUMERIC_DATE.finditer(text):
        d, mo, y = m.groups()
        if y is None and "." in m.group():
            continue  # "12.10" without a year is money, not 12 October
        found.append(((int(d), int(mo), _year(y)), m.span()))
    for m in _DAY_MONTH.finditer(text):
        d, name, y = m.groups()
        if name.lower() in MONTHS:
            found.append(((int(d), MONTHS[name.lower()], _year(y)), m.span()))
    for m in _MONTH_DAY.finditer(text):
        name, d, y = m.groups()
        if name.lower() in MONTHS:
            found.append(((int(d), MONTHS[name.lower()], _year(y)), m.span()))
    return [(day, span) for day, span in found if 1 <= day[0] <= 31 and 1 <= day[1] <= 12]


def read_line(text: str) -> Line:
    spans = _date_spans(text)
    dates = {day for day, _ in spans}
    if any(y is not None for _, _, y in dates):
        dates = {day for day in dates if day[2] is not None}  # a written year is never a wildcard
    amounts = {
        normalise(m.group())
        for m in NUMBER.finditer(text)
        if not any(m.start() < end and start < m.end() for _, (start, end) in spans)
    }
    return Line(text, frozenset(dates), frozenset(amounts))


def dates_in(text: str) -> set[Day]:
    """(day, month, year or None) for every date written in the text (day before month, the
    Malaysian convention; ASSUMED 30)."""
    return set().union(*(read_line(line).dates for line in text.splitlines() or [""]))


def amounts_in(text: str) -> set[str]:
    return set().union(*(read_line(line).amounts for line in text.splitlines() or [""]))


def _ringgit(amount_sen: int) -> str:
    return f"{amount_sen // 100}.{amount_sen % 100:02d}"


def _date_grounded(day: date, dates: frozenset[Day] | set[Day]) -> bool:
    return any(
        d == day.day and m == day.month and (y is None or y == day.year) for d, m, y in dates
    )


def _squash(text: str) -> str:
    return " ".join(text.casefold().split())


def _matches(row: PastedRowIn, line: Line) -> bool:
    return normalise(_ringgit(row.amount_sen)) in line.amounts and _date_grounded(
        row.date, line.dates
    )


def _why_not(row: PastedRowIn, lines: list[Line], used: set[int]) -> str:
    ringgit = _ringgit(row.amount_sen)
    if not any(normalise(ringgit) in line.amounts for line in lines):
        return f"RM {ringgit} is not written in the pasted text."
    if not any(_date_grounded(row.date, line.dates) for line in lines):
        return f"{row.date.isoformat()} is not in the pasted text."
    if any(_matches(row, line) for i, line in enumerate(lines) if i in used):
        return f"The line with RM {ringgit} on {row.date.isoformat()} is already used by a row."
    return f"RM {ringgit} and {row.date.isoformat()} are not on the same line of the pasted text."


def ground_rows(
    rows: list[PastedRowIn], pasted: str
) -> tuple[list[dict[str, Any]], list[Rejected]]:
    """Keep each row that matches its own line of the paste (its amount and its date written on
    that line, each line used once); say why the others went."""
    lines = [read_line(text) for text in pasted.splitlines()]
    used: set[int] = set()
    kept: list[dict[str, Any]] = []
    rejected: list[Rejected] = []
    for index, row in enumerate(rows):
        at = next(
            (i for i, line in enumerate(lines) if i not in used and _matches(row, line)), None
        )
        if at is None:
            rejected.append(Rejected(index, _why_not(row, lines, used)))
            continue
        description = row.description
        if description and _squash(description) not in _squash(lines[at].text):
            description = None  # the model's own words, or another line's, are not this row's
        category = row.category or guess_category(description)
        try:
            clean = ConfirmRow.model_validate(
                {"date": row.date, "amount_sen": row.amount_sen, "type": row.type,
                 "category": category or "Other", "description": description}
            )  # fmt: skip
        except ValidationError as err:
            rejected.append(Rejected(index, f"Not a valid row ({err.errors()[0]['msg']})."))
            continue
        used.add(at)
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
