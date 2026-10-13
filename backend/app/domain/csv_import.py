"""Statement / spreadsheet table -> import preview rows. Pure: rows of text in, rows out, nothing
stored (plan D-29).

Port of v1's CSV path with these changes: stdlib `csv` instead of pandas, sen not floats, and
the direction of a single-column amount file is decided PER FILE — if any amount is negative the
file is signed and positives are income; if none is, the sign carries no information, so rows are
assumed to be expenses (unless the description says income) and flagged for review. Every row the
parser cannot use is reported with a reason; nothing is dropped silently.

A file's own Type and Category columns are taken as written (D-42): the sign rules and the keyword
guess are only the fallback for a cell that is empty or not understood. CSV text and each sheet of
an Excel workbook (read by `app/domain/upload.py`) go through the same code: rows of strings in,
first the header row is found (title lines above it are skipped), then the columns, then the rows.
"""

import csv
import hashlib
import io
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime

from app.domain.categorize import (
    BNPL,
    REFUND,
    TRANSFER,
    canonical_category,
    guess_category,
    guess_type,
)
from app.domain.money import MAX_AMOUNT_SEN, parse_rm

ECHO_LIMIT = 40  # longest piece of a bad cell repeated back in a skip reason
MAX_ROWS = 5000
MAX_COLUMNS = 64
MAX_DATE_CELL = 40  # characters; a longer "date" is junk and not worth 27 parse attempts
SNIFF_CHARS = 4096
SNIFF_LINES = 10
HEADER_SCAN_ROWS = 30  # the header may sit below a title or notes, but not anywhere in the file
READABLE_CHECK_ROWS = 3  # rows under a candidate header that must include one that reads
MIN_YEAR = 2000
DESCRIPTION_LIMIT = 200
CATEGORY_LIMIT = 60  # what the API accepts for a category

DATE_COLUMNS = ("date", "transaction date", "txn date", "posting date", "tarikh")
DESC_COLUMNS = ("description", "details", "transaction details", "item", "narrative", "keterangan")
AMOUNT_COLUMNS = ("amount", "amount (rm)", "amount(rm)", "amaun")
DEBIT_COLUMNS = ("debit", "debit (rm)", "withdrawal")
CREDIT_COLUMNS = ("credit", "credit (rm)", "deposit")
# Whole-header matches only: "Expense Category" is a category column, not the expense amounts.
EXPENSE_COLUMNS = ("expense", "expenses", "spending", "money out")
INCOME_COLUMNS = ("income", "money in")
TYPE_COLUMNS = ("type", "transaction type", "txn type", "jenis")
CATEGORY_COLUMNS = ("category", "kategori")

# What a Type cell may say. Compared lower-case with the spaces collapsed.
_TYPE_WORDS = {
    **dict.fromkeys(("expense", "expenses", "spending", "spend", "debit", "dr", "out"), "expense"),
    **dict.fromkeys(("income", "incomes", "credit", "cr", "deposit", "in"), "income"),
    **dict.fromkeys(("savings", "saving", "save"), "savings"),
}

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
_EMPTY_MARKS = ("-", "\u2013", "\u2014")  # Excel's accounting format shows zero as a dash
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
    notes: tuple[str, ...] = ()  # things the person should know that are not about one row


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


def _delimiter_candidates(sample: str) -> list[str]:
    """Delimiters worth trying, most likely first: judged over the first lines, not just the
    first, because a title line above the table may use a comma the table does not."""
    lines = [line for line in sample.splitlines() if line.strip()][:SNIFF_LINES]
    totals = {d: sum(line.count(d) for line in lines) for d in (",", ";", "\t")}
    ranked = sorted((d for d in totals if totals[d] > 0), key=lambda d: -totals[d])
    return ranked or [","]


def _find_column(
    headers: Sequence[str], candidates: Sequence[str], taken: set[int], substring: bool = True
) -> int | None:
    for exact in (True, False) if substring else (True,):  # exact beats a substring match
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
    type: int | None
    category: int | None

    def needed(self) -> int:
        """Cells a row must have to be readable. Debit, credit, description, type and category may
        be absent: a spreadsheet leaves out trailing empty cells."""
        used = [self.date, self.amount]
        return max(i for i in used if i is not None) + 1


def _locate_columns(header: Sequence[str]) -> _Columns | None:
    """The columns this header row names, or None when it is not a header (no date or amount)."""
    headers = [h.strip().lower() for h in header]
    taken: set[int] = set()
    columns: dict[str, int | None] = {}
    # Each search is (candidates, whole-header-only?). Debit and credit go before "amount":
    # "Debit Amount" is a debit column, not THE amount. Category goes before description so that
    # "Item Category" is not read as the item.
    for name, searches in (
        ("date", ((DATE_COLUMNS, False),)),
        ("debit", ((DEBIT_COLUMNS, False), (EXPENSE_COLUMNS, True))),
        ("credit", ((CREDIT_COLUMNS, False), (INCOME_COLUMNS, True))),
        ("amount", ((AMOUNT_COLUMNS, False),)),
        ("type", ((TYPE_COLUMNS, True),)),
        ("category", ((CATEGORY_COLUMNS, False),)),
        ("description", ((DESC_COLUMNS, False),)),
    ):
        index = None
        for candidates, whole_only in searches:
            index = _find_column(headers, candidates, taken, substring=not whole_only)
            if index is not None:
                taken.add(index)
                break
        columns[name] = index
    has_amount = any(columns[k] is not None for k in ("amount", "debit", "credit"))
    date_index = columns["date"]
    if date_index is None or not has_amount:
        return None
    return _Columns(
        date=date_index,
        description=columns["description"],
        amount=columns["amount"],
        debit=columns["debit"],
        credit=columns["credit"],
        type=columns["type"],
        category=columns["category"],
    )


@dataclass(frozen=True)
class Sheet:
    """One table of cells as text (an Excel sheet, or a whole CSV): blank rows already removed."""

    name: str
    grid: Sequence[Sequence[str]]


@dataclass(frozen=True)
class _Table:
    sheet: str
    columns: _Columns
    body: Sequence[Sequence[str]]
    readable: bool  # one of the first rows under this header reads as a transaction


_NO_ROWS = ("CSV_NO_ROWS", "No usable rows found — check the file has date and amount columns.")
_MISSING_COLUMNS = (
    "CSV_MISSING_COLUMNS",
    "Couldn't find date/amount columns: the file needs a date and an amount column.",
)


def _has_readable_row(columns: _Columns, body: Sequence[Sequence[str]]) -> bool:
    for fields in body[:READABLE_CHECK_ROWS]:
        try:
            _read_row(0, fields, columns, directional=True)
        except _RowProblem:
            continue
        return True
    return False


def _find_table(name: str, grid: Sequence[Sequence[str]]) -> _Table:
    """The header row and the rows under it. A title line can look like a header ("Last updated,
    Amount due"), so the header is the first row that names a date and an amount and has a row
    under it that reads; if none has, the first header-like row is kept so its bad rows are
    reported rather than hidden."""
    if len(grid) < 2:
        raise CsvImportError(*_NO_ROWS)
    first: _Table | None = None
    header_without_rows = False
    for index, row in enumerate(grid[:HEADER_SCAN_ROWS]):
        columns = _locate_columns(row)
        if columns is None:
            continue
        body = grid[index + 1 :]
        if not body:
            header_without_rows = True
            continue
        table = _Table(name, columns, body, _has_readable_row(columns, body))
        if table.readable:
            return table
        first = first or table
    if first is not None:
        return first
    raise CsvImportError(*(_NO_ROWS if header_without_rows else _MISSING_COLUMNS))


def too_many_rows() -> CsvImportError:
    return CsvImportError(
        "CSV_TOO_MANY_ROWS", f"The file has more than {MAX_ROWS:,} rows — import a shorter range."
    )


def too_many_columns() -> CsvImportError:
    return CsvImportError(
        "CSV_PARSE_FAILED", f"The file has more than {MAX_COLUMNS} columns; is it a bank export?"
    )


def _read_delimited(text: str, delimiter: str) -> list[list[str]]:
    """Non-blank rows of delimited text. Reading stops as soon as a limit is crossed, so a 5 MB
    file of one-character rows costs a few thousand rows of memory, not millions."""
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows: list[list[str]] = []
    try:
        for fields in reader:
            if not any(cell.strip() for cell in fields):
                continue
            if len(fields) > MAX_COLUMNS:
                raise too_many_columns()
            rows.append(fields)
            if len(rows) > MAX_ROWS + HEADER_SCAN_ROWS:
                raise too_many_rows()
    except csv.Error as err:  # e.g. a single field over the csv module's size limit
        raise CsvImportError(
            "CSV_PARSE_FAILED", "Couldn't parse this file — is it a valid CSV export?"
        ) from err
    return rows


def _csv_table(text: str) -> _Table:
    """Try the likeliest delimiter first; the next one only if this one gives no table, or a table
    with no row that reads (a wrong delimiter can still find a header-like title line)."""
    text = text.lstrip("﻿")
    failure: CsvImportError | None = None
    fallback: _Table | None = None
    for delimiter in _delimiter_candidates(text[:SNIFF_CHARS]):
        try:
            table = _find_table("", _read_delimited(text, delimiter))
        except CsvImportError as err:
            failure = failure or err
            continue
        if table.readable:
            return table
        fallback = fallback or table
    if fallback is not None:
        return fallback
    raise failure or CsvImportError(*_NO_ROWS)


def parse_csv(text: str) -> ImportPreview:
    return _preview([_csv_table(text)], ())


_SHEET_NOTE_REASON = {
    "CSV_MISSING_COLUMNS": "no date and amount columns found",
    "CSV_NO_ROWS": "no rows under a header",
}


def parse_sheets(sheets: Sequence[Sheet], notes: Sequence[str] = ()) -> ImportPreview:
    """Every sheet that holds a table is read; each one that does not is named in a note."""
    tables: list[_Table] = []
    all_notes = list(notes)
    failure: CsvImportError | None = None
    for sheet in sheets:
        try:
            tables.append(_find_table(sheet.name, sheet.grid))
        except CsvImportError as err:
            failure = failure or err
            reason = _SHEET_NOTE_REASON.get(err.code, err.message)
            all_notes.append(f"Sheet {sheet.name!r} was not read: {reason}.")
    if not tables:
        raise failure or CsvImportError(*_NO_ROWS)
    return _preview(tables, tuple(all_notes))


def _preview(tables: Sequence[_Table], notes: tuple[str, ...]) -> ImportPreview:
    if sum(len(t.body) for t in tables) > MAX_ROWS:
        raise too_many_rows()
    rows: list[ImportRow] = []
    skipped: list[SkippedRow] = []
    all_notes = list(notes)
    for table in tables:
        # Rows are numbered by data row across the whole file, so the numbers stay unique.
        label = f"sheet {table.sheet!r}: " if len(tables) > 1 else ""
        found, bad, table_notes = _read_rows(
            table, first_number=len(rows) + len(skipped) + 1, label=label
        )
        rows += found
        skipped += bad
        all_notes += table_notes
    if not rows:
        raise CsvImportError(*_NO_ROWS)
    return ImportPreview(rows=tuple(rows), skipped=tuple(skipped), notes=tuple(all_notes))


class _RowProblem(ValueError):
    """One row that cannot be used; the message is the reason shown to the person."""


def _is_signed(table: _Table) -> bool:
    """A single amount column with any negative value is signed; with none, direction is unknown."""
    columns = table.columns
    if columns.amount is None:
        return False
    for fields in table.body:
        if len(fields) >= columns.needed():
            try:
                if _signed_amount(fields[columns.amount])[0] < 0:
                    return True
            except ValueError:
                continue
    return False


def _type_column_says_direction(table: _Table) -> bool:
    """False when the Type column has values and not one of them is income, expense or savings
    (a sheet whose "Type" holds Food, Transport...): such a column says nothing about direction."""
    said = [" ".join(_cell(f, table.columns.type).split()).lower() for f in table.body]
    said = [value for value in said if value]
    return not said or any(value in _TYPE_WORDS for value in said)


def _read_rows(
    table: _Table, first_number: int, label: str
) -> tuple[list[ImportRow], list[SkippedRow], list[str]]:
    columns = table.columns
    notes: list[str] = []
    if columns.type is not None and not _type_column_says_direction(table):
        columns = replace(columns, type=None)
        where = f"Sheet {table.sheet!r}: " if label else ""
        notes.append(
            f"{where}The Type column was not used as income or expense: none of its values "
            "said income, expense or savings."
        )
    directional = columns.amount is None or _is_signed(table)
    rows: list[ImportRow] = []
    skipped: list[SkippedRow] = []
    for number, fields in enumerate(table.body, start=first_number):
        try:
            rows.append(_read_row(number, fields, columns, directional))
        except _RowProblem as problem:
            skipped.append(SkippedRow(number, label + str(problem)))
    return rows, skipped, notes


def _cell(fields: Sequence[str], index: int | None) -> str:
    return fields[index] if index is not None and index < len(fields) else ""


def _read_row(
    number: int, fields: Sequence[str], columns: _Columns, directional: bool
) -> ImportRow:
    if len(fields) < columns.needed():
        raise _RowProblem("row has too few columns")
    day = _parse_date(fields[columns.date])
    if day is None:
        raise _RowProblem("unparseable date")
    description = " ".join(_cell(fields, columns.description).split())[:DESCRIPTION_LIMIT] or None
    sign, sen = _read_amount(fields, columns)
    kind, kind_issues = _direction(_cell(fields, columns.type), description, sign, directional)
    category, category_issues = _category(_cell(fields, columns.category), description, kind)
    return ImportRow(
        row=number,
        date=day,
        amount_sen=sen,
        type=kind,
        category_guess=category,
        description=description,
        issues=kind_issues + category_issues,
        fingerprint=fingerprint(day, sen, kind, description),
    )


def _read_amount(fields: Sequence[str], columns: _Columns) -> tuple[int, int]:
    try:
        if columns.amount is None:
            sign, sen = _split_amount(fields, columns)
        else:
            sign, sen = _signed_amount(fields[columns.amount])
    except ValueError as err:
        raise _RowProblem(str(err)) from err
    if sen == 0:
        raise _RowProblem("missing or zero amount")
    if sen > MAX_AMOUNT_SEN:
        raise _RowProblem("amount too large")
    return sign, sen


def _direction(
    raw_type: str, description: str | None, sign: int, directional: bool
) -> tuple[str, tuple[str, ...]]:
    """Income, expense or savings, and what the person should check. The file's Type cell wins; the
    sign (when the file has signs) or the words of the description are the fallback."""
    said = " ".join(raw_type.split()).lower()
    if said in _TYPE_WORDS:
        return _TYPE_WORDS[said], ()
    issues: tuple[str, ...] = ()
    if said:
        issues = (f"type {raw_type.strip()[:ECHO_LIMIT]!r} not recognised — please review",)
    if directional:
        return guess_type(description, sign), issues
    kind = guess_type(description, 0)  # unsigned file: only the words can say "income"
    return kind, issues + ((_NO_SIGN_ISSUE,) if kind == "expense" else (_ASSUMED_INCOME_ISSUE,))


def _category(raw: str, description: str | None, kind: str) -> tuple[str, tuple[str, ...]]:
    """The file's own category as written (the app's spelling when it is one of the app's),
    else a keyword guess. BNPL is assigned by the app to plan payments, never by a file. Refund
    and Transfer change how the forecast treats a row (a refund is netted against spending, a
    transfer is left out of both sides), so a Refund is only taken on income and a Transfer is
    flagged."""
    said = " ".join(raw.split())[:CATEGORY_LIMIT]
    if not said:
        return guess_category(description), ()
    if said.casefold() == BNPL.casefold():
        return guess_category(description), (
            f"category {BNPL!r} is set by the app — please review",
        )
    category = canonical_category(said) or said
    if category == REFUND and kind != "income":
        return guess_category(description), (
            f"category {REFUND!r} is only for money coming back — please review",
        )
    if category == TRANSFER:
        return category, (
            f"category {TRANSFER!r} is left out of spending and income — please review",
        )
    return category, ()


def _split_amount(fields: Sequence[str], columns: _Columns) -> tuple[int, int]:
    """Debit/credit layout: a non-zero debit is an expense, else a non-zero credit is income."""
    for index, sign in ((columns.debit, -1), (columns.credit, 1)):
        cell = _cell(fields, index).strip()
        if not cell or cell in _EMPTY_MARKS:
            continue
        _, sen = _signed_amount(cell)
        if sen:
            return sign, sen
    raise ValueError("missing or zero amount")
