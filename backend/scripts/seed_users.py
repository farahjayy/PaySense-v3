"""Seed a tester account with its passphrase (ADR D-49). Idempotent.

    cd backend && uv run python scripts/seed_users.py --username amir-k7q2xm --display "Amir" \
        --persona frequent_bnpl --passphrase-file ../data/private/amir.pass

The passphrase is read from the file's first line (never a command argument, so it stays out of
shell history). Without --passphrase-file one is generated and printed once: deliver it privately.
Running again with a passphrase replaces it and ends that user's sessions.
Run it from the backend/ directory so backend/.env is found.
"""

import argparse
import sys
from pathlib import Path

from postgrest import APIError

from app.core.passphrase import generate_passphrase
from app.core.settings import MissingSettingsError, load_settings
from app.db.client import build_client
from app.db.users import PERSONAS
from app.seed import seed_user


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--username", required=True)
    parser.add_argument("--display", required=True, help="Display name shown in the app")
    parser.add_argument("--persona", choices=sorted(PERSONAS), default=None)
    parser.add_argument("--passphrase-file", type=Path, default=None)
    args = parser.parse_args()
    generated = args.passphrase_file is None
    if generated:
        passphrase = generate_passphrase()
    else:
        try:
            lines = args.passphrase_file.read_text(encoding="utf-8").splitlines()
        except OSError as err:
            print(f"Cannot read the passphrase file: {err}", file=sys.stderr)
            return 2
        passphrase = lines[0] if lines else ""
    try:
        settings = load_settings()
    except MissingSettingsError as err:
        print(err, file=sys.stderr)
        return 2
    try:
        user, created = seed_user(
            build_client(settings),
            username=args.username,
            display_name=args.display,
            persona=args.persona,
            passphrase=passphrase,
        )
    except ValueError as err:
        print(f"Invalid input: {err}", file=sys.stderr)
        return 2
    except APIError as err:
        print(f"Database error ({err.code}): {err.message}", file=sys.stderr)
        return 1
    print(f"{'Created' if created else 'Already exists'}: {user['username']} ({user['id']})")
    if generated:
        print(f"Passphrase (shown once, deliver privately): {passphrase}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
