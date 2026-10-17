"""A throwaway account on the REAL database for the real-model browser journey (WP1).

    cd backend && uv run python scripts/e2e_real_account.py create --out <file.json>
    cd backend && uv run python scripts/e2e_real_account.py delete --file <file.json>

`create` seeds a user with an unguessable name and writes a persona statement shifted to end
just before today next to the account file; `delete` removes the user, and with it (cascade)
every row the journey wrote. The file holds a username only and lives under gitignored paths.
"""

import argparse
import json
import secrets
import sys
from pathlib import Path

from app.api.deps import malaysia_today
from app.core.settings import MissingSettingsError, load_settings
from app.db import users
from app.db.client import build_client
from app.seed import seed_user
from ml.uat.shift_persona import PERSONA_DIR, read_rows, shift_rows, write_rows

PERSONA = "budget_conscious"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=["create", "delete"])
    parser.add_argument("--out", type=Path)
    parser.add_argument("--file", type=Path)
    args = parser.parse_args()
    try:
        db = build_client(load_settings())
    except MissingSettingsError as err:
        print(err, file=sys.stderr)
        return 2
    if args.action == "create":
        if args.out is None:
            parser.error("create needs --out")
        username = f"rj-{secrets.token_hex(8)}"
        passphrase = secrets.token_urlsafe(18)
        user, _ = seed_user(db, username=username, display_name="Real Journey", persona=PERSONA)
        if hasattr(users, "set_passphrase"):  # WP18 (D-49): login needs a passphrase too
            users.set_passphrase(db, user["id"], passphrase)
        else:
            passphrase = None
        csv_path = args.out.with_suffix(".csv")
        rows = shift_rows(read_rows(PERSONA_DIR / f"{PERSONA}.csv"), malaysia_today())
        write_rows(csv_path, rows)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(
            json.dumps({"username": username, "passphrase": passphrase, "csv": str(csv_path)}),
            encoding="utf-8",
        )
        print(f"created {args.out}")
        return 0
    if args.file is None:
        parser.error("delete needs --file")
    account = json.loads(args.file.read_text(encoding="utf-8"))
    row = users.get_by_username(db, account["username"])
    if row is not None:
        db.table("users").delete().eq("id", row["id"]).execute()
    args.file.unlink(missing_ok=True)
    Path(account["csv"]).unlink(missing_ok=True)
    print("deleted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
