"""Seed every tester in a roster file. Idempotent.

    cd backend && uv run python scripts/seed_testers.py --roster ../uat/testers.csv [--dry-run]

The roster is `participant,username,display,persona` (see uat/testers.template.csv). Run it from
the backend/ directory so backend/.env is found. Persona data is imported by the tester during the
session; this only creates the accounts. Each account gets a generated passphrase (ADR D-49),
written with its username to --passphrases-out (default: data/private/tester_passphrases.csv,
gitignored) for private delivery.
"""

import argparse
import csv
import sys
from pathlib import Path

import httpx
from postgrest import APIError

from app.core.passphrase import generate_passphrase
from app.core.settings import MissingSettingsError, load_settings
from app.db.client import build_client
from app.seed import seed_user
from ml.uat.load import UatDataError
from ml.uat.roster import load_roster


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--roster", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", help="list what would be created")
    parser.add_argument(
        "--passphrases-out",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data" / "private" / "tester_passphrases.csv",
    )
    args = parser.parse_args()
    try:
        testers = load_roster(args.roster)
    except (UatDataError, FileNotFoundError) as err:
        print(f"Invalid roster: {err}", file=sys.stderr)
        return 2
    if args.dry_run:
        for t in testers:
            print(f"Would seed {t.participant}: {t.username} ({t.persona})")
        return 0
    try:
        client = build_client(load_settings())
    except MissingSettingsError as err:
        print(err, file=sys.stderr)
        return 2
    issued: list[tuple[str, str, str]] = []
    for t in testers:
        passphrase = generate_passphrase()
        try:
            user, created = seed_user(
                client,
                username=t.username,
                display_name=t.display,
                persona=t.persona,
                passphrase=passphrase,
            )
        except (ValueError, APIError, httpx.HTTPError) as err:
            print(f"{t.participant}: {err}", file=sys.stderr)
            return 1
        issued.append((t.participant, user["username"], passphrase))
        print(f"{t.participant}: {'created' if created else 'already exists'} {user['username']}")
        if not created and (
            user.get("persona") != t.persona or user.get("display_name") != t.display
        ):
            print(
                f"{t.participant}: warning - the existing account has persona "
                f"{user.get('persona')!r}, not {t.persona!r} (or a different display name)",
                file=sys.stderr,
            )
    args.passphrases_out.parent.mkdir(parents=True, exist_ok=True)
    with args.passphrases_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["participant", "username", "passphrase"])
        writer.writerows(issued)
    print(f"Passphrases written to {args.passphrases_out} (deliver privately; never commit).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
