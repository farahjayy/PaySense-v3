"""Move a persona CSV forward so it ends just before the session date.

    cd backend && uv run python -m ml.uat.shift_persona --persona budget_conscious \
        --out ../uat/data/budget_conscious_shifted.csv [--session 2026-11-03]

The persona statements were written for a fixed period. Imported unchanged, a tester would see a
ledger months out of date and a forecast flagged as stale. Every date moves by the same whole
number of weeks, so weekday patterns and the gaps between payments survive. A whole-week shift
does not keep a date on the same day of the month, so a payment on the 1st will land on another
day; the forecast reads the pattern of weeks, not the calendar. Amounts and descriptions are
untouched.
"""

import argparse
import csv
import re
import sys
from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path

from ml.uat.errors import UatDataError

PERSONA_DIR = Path(__file__).resolve().parents[3] / "data" / "personas"
DATE_FORMAT = "%d/%m/%Y"
COLUMNS = ["Date", "Description", "Amount"]
DAYS_PER_WEEK = 7
PERSONA_NAME = re.compile(r"[a-z][a-z0-9_]*")


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise UatDataError(f"{path.name}: header must be {','.join(COLUMNS)}")
        rows = []
        for line, row in enumerate(reader, start=2):
            if None in row or any(value is None for value in row.values()):
                raise UatDataError(
                    f"{path.name} row {line}: expected exactly {len(COLUMNS)} columns"
                )
            rows.append(row)
    if not rows:
        raise UatDataError(f"{path.name}: no rows")
    return rows


def _parse(row: dict[str, str], line: int) -> date:
    try:
        return datetime.strptime(row["Date"], DATE_FORMAT).date()
    except ValueError:
        raise UatDataError(f"row {line}: date {row['Date']!r} is not DD/MM/YYYY") from None


def weeks_to_shift(last_date: date, session: date) -> int:
    """Whole weeks to move so the last date is within a week of the day before the session."""
    gap_days = (session - timedelta(days=1) - last_date).days
    return gap_days // DAYS_PER_WEEK


def shift_rows(rows: Sequence[dict[str, str]], session: date) -> list[dict[str, str]]:
    """A new list with every date moved by the same whole number of weeks."""
    dates = [_parse(row, i) for i, row in enumerate(rows, start=2)]
    shift = timedelta(weeks=weeks_to_shift(max(dates), session))
    return [
        {**row, "Date": (d + shift).strftime(DATE_FORMAT)}
        for row, d in zip(rows, dates, strict=True)
    ]


def write_rows(path: Path, rows: Sequence[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--persona", help="a name in data/personas/, e.g. budget_conscious")
    source.add_argument("--csv", type=Path, help="any statement in the persona format")
    parser.add_argument("--session", type=date.fromisoformat, default=None, help="default: today")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.csv is None and not PERSONA_NAME.fullmatch(args.persona):
        print(f"Cannot shift: persona {args.persona!r} is not a persona name", file=sys.stderr)
        return 2
    path = args.csv or PERSONA_DIR / f"{args.persona}.csv"
    if args.out.resolve() == path.resolve():
        print("Cannot shift: --out would overwrite the source file", file=sys.stderr)
        return 2
    session = args.session or date.today()
    try:
        shifted = shift_rows(read_rows(path), session)
    except (UatDataError, FileNotFoundError) as err:
        print(f"Cannot shift: {err}", file=sys.stderr)
        return 2
    write_rows(args.out, shifted)
    ends = max(datetime.strptime(r["Date"], DATE_FORMAT).date() for r in shifted)
    print(f"Wrote {len(shifted)} rows to {args.out}; the last transaction is {ends.isoformat()}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
