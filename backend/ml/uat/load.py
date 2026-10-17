"""Reading and validating the response files. A bad row is an error that names it, never a
silently smaller sample."""

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from ml.uat.errors import UatDataError
from ml.uat.sus import LIKERT_MAX, LIKERT_MIN, SUS_ITEMS

CLARITY_ITEMS = 4
INVENTED_MARK = "# INVENTED"


@dataclass(frozen=True)
class Option:
    id: str
    text: str
    risk_rank: int  # higher = riskier


@dataclass(frozen=True)
class Vignette:
    id: str
    title: str
    options: tuple[Option, ...]

    def option(self, option_id: str) -> Option | None:
        return next((o for o in self.options if o.id == option_id), None)


@dataclass(frozen=True)
class Choice:
    participant: str
    vignette: str
    phase: str  # "pre" | "post"
    option: str
    confidence: int


def clean_row(name: str, line: int, row: Mapping[str | None, str | None]) -> dict[str, str]:
    """A CSV row with stripped text; a row with more fields than the header is an error."""
    if None in row:  # csv.DictReader keeps the surplus fields under a None key
        raise UatDataError(f"{name} row {line}: too many columns")
    return {str(k).strip(): (v or "").strip() for k, v in row.items()}


def _rows(path: Path, columns: list[str]) -> tuple[list[dict[str, str]], bool]:
    """Data rows of a CSV, skipping '#' comment lines; also whether it is marked invented."""
    text = path.read_text(encoding="utf-8-sig")
    invented = text.lstrip().startswith(INVENTED_MARK)
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    reader = csv.DictReader(lines)
    if reader.fieldnames is None or [c.strip() for c in reader.fieldnames] != columns:
        raise UatDataError(f"{path.name}: header must be {','.join(columns)}")
    rows = [clean_row(path.name, line, row) for line, row in enumerate(reader, start=2)]
    return rows, invented


def _likert(path: Path, line: int, name: str, value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise UatDataError(f"{path.name} row {line}: {name} must be a whole number") from None
    if not LIKERT_MIN <= number <= LIKERT_MAX:
        raise UatDataError(f"{path.name} row {line}: {name} must be {LIKERT_MIN}-{LIKERT_MAX}")
    return number


def _scale_file(path: Path, prefix: str, count: int) -> tuple[dict[str, list[int]], bool]:
    columns = ["participant", *[f"{prefix}{i}" for i in range(1, count + 1)]]
    rows, invented = _rows(path, columns)
    out: dict[str, list[int]] = {}
    for line, row in enumerate(rows, start=2):
        who = row["participant"]
        if not who:
            raise UatDataError(f"{path.name} row {line}: participant is empty")
        if who in out:
            raise UatDataError(f"{path.name} row {line}: {who} appears twice")
        out[who] = [_likert(path, line, c, row[c]) for c in columns[1:]]
    if not out:
        raise UatDataError(f"{path.name}: no responses")
    return out, invented


def load_sus(path: Path) -> tuple[dict[str, list[int]], bool]:
    return _scale_file(path, "s", SUS_ITEMS)


def load_clarity(path: Path) -> tuple[dict[str, list[int]], bool]:
    return _scale_file(path, "c", CLARITY_ITEMS)


def load_vignettes(path: Path) -> dict[str, Vignette]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        out: dict[str, Vignette] = {}
        for item in raw["vignettes"]:
            vignette_id = str(item["id"])
            if vignette_id in out:
                raise UatDataError(f"{path.name}: vignette {vignette_id} is listed twice")
            options = tuple(
                Option(str(o["id"]), str(o["text"]), int(o["risk_rank"])) for o in item["options"]
            )
            out[vignette_id] = Vignette(vignette_id, str(item["title"]), options)
    except (yaml.YAMLError, KeyError, TypeError, ValueError) as err:
        if isinstance(err, UatDataError):
            raise
        missing = f" (missing {err})" if isinstance(err, KeyError) else ""
        raise UatDataError(f"{path.name}: not a valid vignette file{missing}") from err
    return out


def load_choices(path: Path, vignettes: Mapping[str, Vignette]) -> tuple[list[Choice], bool]:
    columns = ["participant", "vignette", "phase", "option", "confidence"]
    rows, invented = _rows(path, columns)
    choices: list[Choice] = []
    seen: set[tuple[str, str, str]] = set()
    for line, row in enumerate(rows, start=2):
        vignette = vignettes.get(row["vignette"])
        if vignette is None:
            raise UatDataError(f"{path.name} row {line}: unknown vignette {row['vignette']!r}")
        if row["phase"] not in ("pre", "post"):
            raise UatDataError(f"{path.name} row {line}: phase must be pre or post")
        if vignette.option(row["option"]) is None:
            raise UatDataError(f"{path.name} row {line}: unknown option {row['option']!r}")
        key = (row["participant"], row["vignette"], row["phase"])
        if not row["participant"] or key in seen:
            raise UatDataError(f"{path.name} row {line}: missing or repeated answer {key}")
        seen.add(key)
        choices.append(
            Choice(
                row["participant"],
                row["vignette"],
                row["phase"],
                row["option"],
                _likert(path, line, "confidence", row["confidence"]),
            )
        )
    if not choices:
        raise UatDataError(f"{path.name}: no responses")
    return choices, invented
