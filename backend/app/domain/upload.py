"""An uploaded file's bytes -> import preview (D-42). Pure: nothing is stored.

Text files (CSV, TSV, plain text) and Excel workbooks (.xlsx, .xlsm) both end up as rows of text and
go through `app/domain/csv_import.py`. A workbook is a zip file from a stranger, so it is checked
before it is parsed: how big it becomes when unpacked (in total and per part), how many parts it
has, and, by a streaming pass that keeps no tree, how many cells a row and a sheet hold (openpyxl
builds every cell of a row before it applies a column limit, so a 10 KB file with two million cells
in one row would otherwise exhaust a small worker). Rows scanned are budgeted across all sheets, and
at most two workbooks are read at once. XML entity expansion is blocked by `defusedxml`, which
openpyxl uses when it is installed (a test fails if that stops being true). Macros are never run:
openpyxl does not load them.
"""

import codecs
import io
import logging
import math
import threading
import zipfile
from datetime import date, datetime
from itertools import islice
from typing import Any, Literal
from xml.parsers import expat  # noqa: S408  (DTDs are refused below)

from openpyxl import load_workbook

from app.domain.csv_import import (
    HEADER_SCAN_ROWS,
    MAX_COLUMNS,
    MAX_ROWS,
    CsvImportError,
    ImportPreview,
    Sheet,
    parse_csv,
    parse_sheets,
    too_many_columns,
    too_many_rows,
)

logger = logging.getLogger("paysense")

FileKind = Literal["text", "excel"]
TEXT_EXTENSIONS = (".csv", ".tsv", ".txt")
EXCEL_EXTENSIONS = (".xlsx", ".xlsm")

MAX_WORKBOOK_UNCOMPRESSED = 20 * 1024 * 1024  # bytes; a 5,000-row statement unpacks to ~1 MB
MAX_WORKBOOK_PARTS = 500
MAX_WORKSHEET_BYTES = 8 * 1024 * 1024  # any one XML part
MAX_SHARED_STRINGS_BYTES = 2 * 1024 * 1024  # openpyxl loads this whole table up front
MAX_CELLS_PER_SHEET = 200_000  # 5,000 rows of 40 columns; a real statement is far smaller
MAX_SHEETS = 20
MAX_SCAN_ROWS = 10_000  # rows looked at per sheet, blank ones included (a stray far-away cell)
MAX_TOTAL_SCAN_ROWS = 30_000  # across all sheets, so sheets that share one part cost once
MAX_CONCURRENT_WORKBOOKS = 2
GATE_WAIT_SECONDS = 10.0
_GATE = threading.BoundedSemaphore(MAX_CONCURRENT_WORKBOOKS)
FLOAT_NOISE = 1e-9  # relative: a float this close to a whole sen is Excel's binary noise


_LIMIT_REASON = {
    "CSV_TOO_MANY_ROWS": f"it has more than {MAX_ROWS:,} rows",
    "CSV_PARSE_FAILED": f"it has more than {MAX_COLUMNS} columns",
}


def file_kind(filename: str | None) -> FileKind:
    name = (filename or "").lower()
    if name.endswith(TEXT_EXTENSIONS):
        return "text"
    if name.endswith(EXCEL_EXTENSIONS):
        return "excel"
    if name.endswith(".xls"):
        raise CsvImportError(
            "WRONG_FILE_TYPE",
            "Old Excel files (.xls) can't be read. In Excel choose File > Save As and pick "
            "Excel Workbook (.xlsx) or CSV, then upload that file.",
        )
    raise CsvImportError("WRONG_FILE_TYPE", "Please upload a CSV or Excel (.xlsx) file.")


def decode_text(data: bytes) -> str:
    """UTF-8 (with or without a byte order mark), Excel's UTF-16 "Unicode Text", or else
    Windows-1252, which is what Excel's plain "CSV (Comma delimited)" writes on Windows."""
    if data.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return data.decode("utf-16", errors="replace")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def parse_upload(kind: FileKind, data: bytes) -> ImportPreview:
    """Bytes of an accepted file (see `file_kind`) to a preview; CsvImportError if unusable."""
    if kind == "excel":
        # Reading a workbook is CPU-bound Python; a few at a time, the rest wait their turn.
        if not _GATE.acquire(timeout=GATE_WAIT_SECONDS):
            raise CsvImportError(
                "IMPORT_BUSY", "Other files are being read right now. Try again in a moment."
            )
        try:
            sheets, notes = read_workbook(data)
            return parse_sheets(sheets, notes)
        finally:
            _GATE.release()
    return parse_csv(decode_text(data))


def _unreadable() -> CsvImportError:
    return CsvImportError(
        "EXCEL_UNREADABLE",
        "Couldn't read this Excel file. If it is password-protected, remove the password and "
        "save it again; otherwise try saving it as .xlsx or CSV from Excel.",
    )


def _too_large() -> CsvImportError:
    return CsvImportError(
        "EXCEL_TOO_LARGE", "This workbook is too large to read. Export a shorter date range."
    )


def _check_archive(data: bytes) -> None:
    """Refuse a hostile workbook before openpyxl sees it: too big unpacked (in total or in one
    part), too many parts, or a sheet with too many cells. CPython's zipfile stops reading a part at
    its declared size, so the declared sizes are a real bound."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            parts = archive.infolist()
            if len(parts) > MAX_WORKBOOK_PARTS:
                raise _too_large()
            if sum(p.file_size for p in parts) > MAX_WORKBOOK_UNCOMPRESSED:
                raise _too_large()
            for part in parts:
                _check_part(archive, part)
    except CsvImportError:
        raise
    except Exception as err:  # a hostile file can fail in many ways; all of them mean "no"
        raise _unreadable() from err


def _check_part(archive: zipfile.ZipFile, part: zipfile.ZipInfo) -> None:
    name = part.filename.lower()
    if not name.endswith(".xml"):
        return
    if part.file_size > _part_limit(name):
        raise _too_large()
    _scan_cells(archive, part)


def _part_limit(name: str) -> int:
    return MAX_SHARED_STRINGS_BYTES if name.endswith("sharedstrings.xml") else MAX_WORKSHEET_BYTES


def _scan_cells(archive: zipfile.ZipFile, part: zipfile.ZipInfo) -> None:
    """Stream one XML part, counting `<c>` cells per row and per part, keeping nothing. A DTD or
    entity declaration is refused outright."""
    row_cells = 0
    cells = 0

    def refuse(*_args: object) -> None:
        raise _unreadable()

    def start(name: str, _attributes: object) -> None:
        nonlocal row_cells, cells
        local = name.rsplit("}", 1)[-1]
        if local == "row":
            row_cells = 0
        elif local == "c":
            row_cells += 1
            cells += 1
            if row_cells > MAX_COLUMNS + 1:
                raise too_many_columns()
            if cells > MAX_CELLS_PER_SHEET:
                raise _too_large()

    parser = expat.ParserCreate(namespace_separator="}")
    parser.StartElementHandler = start
    parser.StartDoctypeDeclHandler = refuse
    parser.EntityDeclHandler = refuse
    parser.ExternalEntityRefHandler = refuse
    with archive.open(part) as stream:
        while chunk := stream.read(64 * 1024):
            parser.Parse(chunk, False)
    parser.Parse(b"", True)


def read_workbook(data: bytes) -> tuple[list[Sheet], list[str]]:
    """The visible sheets of a workbook as text tables, and notes about any sheet not read."""
    _check_archive(data)
    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as err:
        logger.warning("Workbook could not be opened: %s", type(err).__name__)
        raise _unreadable() from err
    try:
        return _read_sheets(workbook)
    except CsvImportError:
        raise
    except Exception as err:
        logger.warning("Workbook could not be read: %s", type(err).__name__)
        raise _unreadable() from err
    finally:
        workbook.close()


class _ScanBudget:
    """Rows looked at across the whole workbook, so many sheets cannot add up to unbounded work."""

    def __init__(self, limit: int) -> None:
        self.left = limit

    def spend(self) -> None:
        self.left -= 1
        if self.left < 0:
            raise _BudgetSpent("CSV_TOO_MANY_ROWS", too_many_rows().message)


class _BudgetSpent(CsvImportError):
    """The whole workbook is too big to read, not just one sheet."""


def _read_sheets(workbook: Any) -> tuple[list[Sheet], list[str]]:
    sheets: list[Sheet] = []
    notes: list[str] = []
    first_error: CsvImportError | None = None
    budget = _ScanBudget(MAX_TOTAL_SCAN_ROWS)
    for index, worksheet in enumerate(workbook.worksheets):
        if index >= MAX_SHEETS:
            notes.append(f"Only the first {MAX_SHEETS} sheets were read.")
            break
        if worksheet.sheet_state != "visible":
            notes.append(f"Sheet {worksheet.title!r} is hidden, so it was not read.")
            continue
        try:
            sheets.append(Sheet(worksheet.title, _read_grid(worksheet, budget)))
        except _BudgetSpent:
            raise
        except CsvImportError as err:  # one oversized sheet must not sink the others
            first_error = first_error or err
            reason = _LIMIT_REASON.get(err.code, err.message)
            notes.append(f"Sheet {worksheet.title!r} was not read: {reason}.")
    if not sheets and first_error is not None:
        raise first_error
    return sheets, notes


def _read_grid(worksheet: Any, budget: _ScanBudget) -> list[list[str]]:
    grid: list[list[str]] = []
    # One column past the limit, so a row that is too wide is seen as too wide.
    rows = worksheet.iter_rows(max_col=MAX_COLUMNS + 1, values_only=True)
    for values in islice(rows, MAX_SCAN_ROWS):
        budget.spend()
        cells = [_cell_text(value) for value in values]
        while cells and not cells[-1].strip():
            cells.pop()
        if not cells:
            continue
        if len(cells) > MAX_COLUMNS:
            raise too_many_columns()
        grid.append(cells)
        if len(grid) > MAX_ROWS + HEADER_SCAN_ROWS:
            raise too_many_rows()
    # Trailing blanks were trimmed to find blank rows; put them back so that an empty last cell is
    # an empty cell ("missing amount"), not a row "with too few columns".
    width = max((len(row) for row in grid), default=0)
    return [row + [""] * (width - len(row)) for row in grid]


def _cell_text(value: object) -> str:
    """A cell as the text a CSV of the same sheet would hold: dates as ISO, numbers as Excel shows
    them. Money is never multiplied here; the amount is parsed from this text (D-16)."""
    if value is None:
        return ""
    if isinstance(value, datetime):  # before date: a datetime is a date
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return _float_text(value)
    return str(value)


def _float_text(value: float) -> str:
    """12 * 1.1 is stored as 13.200000000000001 though Excel shows 13.2; that noise is removed.
    A float that really has a third decimal is left as it is, so the amount parser refuses it."""
    if not math.isfinite(value):
        return str(value)
    rounded = round(value, 2)
    noise = FLOAT_NOISE * max(1.0, abs(value))
    return f"{rounded:.2f}" if abs(value - rounded) < noise else repr(value)
