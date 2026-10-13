"""The tester roster: who gets which practice account. Parsed and validated, never guessed."""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from app.db.users import PERSONAS, USERNAME_PATTERN
from ml.uat.load import UatDataError, clean_row

COLUMNS = ["participant", "username", "display", "persona"]
# Login takes only a username, so a predictable one lets a stranger sign in as that tester.
GUESSABLE = re.compile(r"^(tester|user|test|participant|p)[-_.]?\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class Tester:
    participant: str
    username: str
    display: str
    persona: str


def load_roster(path: Path) -> list[Tester]:
    lines = [
        line
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    reader = csv.DictReader(lines)
    if reader.fieldnames is None or [c.strip() for c in reader.fieldnames] != COLUMNS:
        raise UatDataError(f"{path.name}: header must be {','.join(COLUMNS)}")
    testers: list[Tester] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for line, row in enumerate(reader, start=2):
        clean = clean_row(path.name, line, row)
        who, username = clean["participant"], clean["username"]
        if not who or not clean["display"]:
            raise UatDataError(f"{path.name} row {line}: participant and display are required")
        if not USERNAME_PATTERN.fullmatch(username):
            raise UatDataError(f"{path.name} row {line}: username {username!r} is not allowed")
        if GUESSABLE.fullmatch(username):
            raise UatDataError(
                f"{path.name} row {line}: username {username!r} is guessable; add random "
                "characters, e.g. p01-k7q2xm"
            )
        if clean["persona"] not in PERSONAS:
            raise UatDataError(f"{path.name} row {line}: persona must be one of {sorted(PERSONAS)}")
        if who in seen_ids or username.lower() in seen_names:
            raise UatDataError(f"{path.name} row {line}: {who} / {username} is a duplicate")
        seen_ids.add(who)
        seen_names.add(username.lower())
        testers.append(Tester(who, username, clean["display"], clean["persona"]))
    if not testers:
        raise UatDataError(f"{path.name}: no testers listed")
    return testers
