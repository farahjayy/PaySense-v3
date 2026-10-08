"""Seed a tester account. Idempotent.

    cd backend && uv run python scripts/seed_users.py --username amir --display "Amir" \
        --persona frequent_bnpl
"""

import argparse
import sys

from app.core.settings import MissingSettingsError, load_settings
from app.db.client import build_client
from app.db.users import PERSONAS
from app.seed import seed_user


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--username", required=True)
    parser.add_argument("--display", required=True, help="Display name shown in the app")
    parser.add_argument("--persona", choices=sorted(PERSONAS), default=None)
    args = parser.parse_args()
    try:
        settings = load_settings()
    except MissingSettingsError as err:
        print(err, file=sys.stderr)
        return 2
    user, created = seed_user(
        build_client(settings),
        username=args.username,
        display_name=args.display,
        persona=args.persona,
    )
    print(f"{'Created' if created else 'Already exists'}: {user['username']} ({user['id']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
