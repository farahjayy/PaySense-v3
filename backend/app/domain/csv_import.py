"""Bank / persona CSV -> import preview rows. Pure: text in, rows out, nothing stored (plan D-29).

Port of v1's CSV path with these changes: stdlib `csv` instead of pandas, sen not floats, and
the direction of a single-column amount file is decided PER FILE — if any amount is negative the
file is signed and positives are income; if none is, the sign carries no information, so rows are
assumed to be expenses (unless the description says income) and flagged for review. Every row the
parser cannot use is reported with a reason; nothing is dropped silently.
"""

import csv
import hashlib
import io
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime

from app.domain.categorize import guess_category, guess_type
from app.domain.money import MAX_AMOUNT_SEN, parse_rm

ECHO_LIMIT = 40  # longest piece of a bad cell repeated back in a skip reason
MAX_ROWS = 5000
MAX_COLUMNS = 64
MAX_DATE_CELL = 40  # characters; a longer "date" is junk and not worth 27 parse attempts
SNIFF_CHARS = 4096
MIN_YEAR = 2000
DESCRIPTION_LIMIT = 200

DATE_COLUMNS = ("date", "transaction date", "txn date", "posting date", "tarikh")
DESC_COLUMNS = ("description", "details", "transaction details", "item", "narrative", "keterangan")
AMOUNT_COLUMNS = ("amount", "amount (rm)", "amount(rm)", "amaun")
DEBIT_COLUMNS = ("debit", "debit (rm)", "withdrawal")
CREDIT_COLUMNS = ("credit", "credit (rm)", "deposit")

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d %b %Y",
    "%d-%b-%Y",
    "%d %B %Y",
    "%d-%B-%Y",
    "%Y/%m/%d",
)
_NO_SIGN_ISSUE = "no sign on amount — assumed expense, please review"
_ASSUMED_INCOME_ISSUE = "no sign on amount — assumed income from the description, please review"


class CsvImportError(ValueError):
    """The file as a whole cannot be imported. `code` is stable; `message` is user-facing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ImportRow:
    row: int
    date: date
    amount_sen: int
    type: str
    category_guess: str
    description: str | None
    issues: tuple[str, ...]
    fingerprint: str
    duplicate: bool = False


@dataclass(frozen=True)
class SkippedRow:
    row: int
    reason: str


@dataclass(frozen=True)
class ImportPreview:
    rows: tuple[ImportRow, ...]
    skipped: tuple[SkippedRow, ...]


def fingerprint(day: date, amount_sen: int, kind: str, description: str | None) -> str:
    """Identity of a transaction for duplicate detection (same day, amount, direction, words)."""
    words = " ".join((description or "").lower().split())
    return hashlib.sha256(f"{day.isoformat()}|{amount_sen}|{kind}|{words}".encode()).hexdigest()[
        :16
    ]


def flag_duplicates(
    rows: Iterable[ImportRow], existing_fingerprints: Iterable[str]
) -> tuple[ImportRow, ...]:
    """Mark rows already stored. Multiplicity-aware: with one stored copy of an identical pair of
    purchases, only the first row of the pair is a duplicate."""
    remaining = Counter(existing_fingerprints)
    flagged = []
    for row in rows:
        if remaining[row.fingerprint] > 0:
            remaining[row.fingerprint] -= 1
            flagged.append(replace(row, duplicate=True))
        else:
            flagged.append(row)
    return tuple(flagged)


def _sniff_delimiter(text: str) -> str:
    first = next((line for line in text.splitlines() if line.strip()), "")
    counts = {d: first.count(d) for d in (",", ";", "\t")}
    best = max(counts, key=lambda d: counts[d])
    return best if counts[best] > 0 else ","


def _find_column(headers: Sequence[str], candidates: Sequence[str], taken: set[int]) -> int | None:
    for exact in (True, False):  # exact header match beats a substring match
        for candidate in candidates:
            for index, header in enumerate(headers):
                if index in taken:
                    continue
                if header == candidate or (not exact and candidate in header):
                    return index
    return None


def _parse_date(raw: str) -> date | None:
    text = raw.strip()
    if len(text) > MAX_DATE_CELL:
        return None
    attempts = [text, text.split("T")[0], text.split()[0] if text.split() else text]
    for attempt in attempts:
        for fmt in _DATE_FORMATS:
            try:
                parsed = datetime.strptime(attempt, fmt).date()
            except ValueError:
                continue
            if parsed.year >= MIN_YEAR:
                return parsed
    return None


def _signed_amount(raw: str) -> tuple[int, int]:
    """(sign, sen) for one amount cell; ValueError("missing amount" / "invalid amount ...")."""
    text = raw.strip()
    if not text:
        raise ValueError("missing amount")
    upper = text.upper()
    negative = (
        (text.startswith("(") and text.endswith(")"))
        or text.startswith("-")
        or text.endswith("-")
        or upper.endswith("DR")
    )
    cleaned = text.strip("()")
    for marker in ("-", "+"):
        cleaned = cleaned.strip(marker)
    for suffix in ("DR", "CR"):
        if cleaned.upper().endswith(suffix):
            cleaned = cleaned[: -len(suffix)]
    try:
        sen = parse_rm(cleaned.strip())
    except ValueError as err:
        raise ValueError(f"invalid amount {text[:ECHO_LIMIT]!r}") from err
    return (-1 if negative else 1), sen


@dataclass(frozen=True)
class _Columns:
    date: int
    description: int | None
    amount: int | None
    debit: int | None
    credit: int | None

    def needed(self) -> int:
        used = [self.date, self.description, self.amount, self.debit, self.credit]
        return max(i for i in used if i is not None) + 1


def _locate_columns(header: Sequence[str]) -> _Columns:
    headers = [h.strip().lower() for h in header]
    taken: set[int] = set()
    columns = {}
    for name, candidates in (
        ("date", DATE_COLUMNS),
        (
            "debit",
            DEBIT_COLUMNS,
        ),  # before "amount": "Debit Amount" is a debit column, not THE amount
        ("credit", CREDIT_COLUMNS),
        ("amount", AMOUNT_COLUMNS),
        ("description", DESC_COLUMNS),
    ):
        index = _find_column(headers, candidates, taken)
        if index is not None:
            taken.add(index)
        columns[name] = index
    if columns["date"] is None or (
        columns["amount"] is None and columns["debit"] is None and columns["credit"] is None
    ):
        raise CsvImportError(
            "CSV_MISSING_COLUMNS",
            "Couldn't find date/amount columns: the file needs a date and an amount column.",
        )
    return _Columns(**columns)


def _data_rows(text: str) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """Header plus numbered data rows. Reading stops as soon as a limit is crossed, so a 5 MB file
    of one-character rows costs a few thousand rows of memory, not millions."""
    text = text.lstrip("﻿")
    reader = csv.reader(io.StringIO(text), delimiter=_sniff_delimiter(text[:SNIFF_CHARS]))
    rows: list[list[str]] = []
    try:
        for fields in reader:
            if not any(cell.strip() for cell in fields):
                continue
            rows.append(fields)
            if len(rows) > MAX_ROWS + 1:
                raise CsvImportError(
                    "CSV_TOO_MANY_ROWS",
                    f"The file has more than {MAX_ROWS:,} rows — import a shorter date range.",
                )
    except csv.Error as err:  # e.g. a single field over the csv module's size limit
        raise CsvImportError(
            "CSV_PARSE_FAILED", "Couldn't parse this file — is it a valid CSV export?"
        ) from err
    if len(rows) < 2:
        raise CsvImportError(
            "CSV_NO_ROWS", "No usable rows found — check the file has date and amount columns."
        )
    header, body = rows[0], rows[1:]
    if len(header) > MAX_COLUMNS:
        raise CsvImportError(
            "CSV_PARSE_FAILED",
            f"The file has more than {MAX_COLUMNS} columns; is it a bank export?",
        )
    return header, list(enumerate(body, start=1))


def parse_csv(text: str) -> ImportPreview:
    header, body = _data_rows(text)
    columns = _locate_columns(header)
    split_amounts = columns.amount is None
    # A single amount column with any negative value is signed; with none, direction is unknown.
    signed_file = False
    if columns.amount is not None:
        for _, fields in body:
            if len(fields) >= columns.needed():
                try:
                    signed_file = signed_file or _signed_amount(fields[columns.amount])[0] < 0
                except ValueError:
                    continue

    rows: list[ImportRow] = []
    skipped: list[SkippedRow] = []
    for number, fields in body:
        if len(fields) < columns.needed():
            skipped.append(SkippedRow(number, "row has too few columns"))
            continue
        day = _parse_date(fields[columns.date])
        if day is None:
            skipped.append(SkippedRow(number, "unparseable date"))
            continue
        description = None
        if columns.description is not None:
            description = " ".join(fields[columns.description].split())[:DESCRIPTION_LIMIT] or None
        try:
            if split_amounts:
                sign, sen = _split_amount(fields, columns)
            else:
                sign, sen = _signed_amount(fields[columns.amount])  # type: ignore[index]
        except ValueError as err:
            skipped.append(SkippedRow(number, str(err)))
            continue
        if sen == 0:
            skipped.append(SkippedRow(number, "missing or zero amount"))
            continue
        if sen > MAX_AMOUNT_SEN:
            skipped.append(SkippedRow(number, "amount too large"))
            continue
        issues: tuple[str, ...] = ()
        if split_amounts or signed_file:
            kind = guess_type(description, sign)
        else:
            kind = guess_type(description, 0)  # unsigned file: only the words can say "income"
            issues = (_NO_SIGN_ISSUE,) if kind == "expense" else (_ASSUMED_INCOME_ISSUE,)
        rows.append(
            ImportRow(
                row=number,
                date=day,
                amount_sen=sen,
                type=kind,
                category_guess=guess_category(description),
                description=description,
                issues=issues,
                fingerprint=fingerprint(day, sen, kind, description),
            )
        )
    if not rows:
        raise CsvImportError(
            "CSV_NO_ROWS", "No usable rows found — check the file has date and amount columns."
        )
    return ImportPreview(rows=tuple(rows), skipped=tuple(skipped))


def _split_amount(fields: Sequence[str], columns: _Columns) -> tuple[int, int]:
    """Debit/credit layout: a non-zero debit is an expense, else a non-zero credit is income."""
    for index, sign in ((columns.debit, -1), (columns.credit, 1)):
        if index is None or not fields[index].strip():
            continue
        _, sen = _signed_amount(fields[index])
        if sen:
            return sign, sen
    raise ValueError("missing or zero amount")
