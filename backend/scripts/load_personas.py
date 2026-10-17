"""Seed the three persona accounts and load each persona's statement through the running API.

    cd backend && uv run python scripts/load_personas.py --api http://localhost:8000

For each persona: seed an account with an unguessable username (kept only in
`data/private/persona_accounts.json`, never in the repo), shift the persona CSV so it ends just
before today, import it through the real API (preview, then confirm the rows that are not
duplicates), confirm the recurring items the app detects (what a tester does on the Recurring
screen), then ask for the forecast. Idempotent: a second run reuses the stored usernames and
imports nothing twice (the preview flags every row as a duplicate).
"""

import argparse
import csv
import io
import json
import secrets
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx

from app.db.client import Database
from app.seed import seed_user
from ml.uat.shift_persona import COLUMNS, PERSONA_DIR, read_rows, shift_rows

ROOT = Path(__file__).resolve().parents[2]
ACCOUNTS_FILE = ROOT / "data" / "private" / "persona_accounts.json"
PERSONAS = {
    "frequent_bnpl": "Aina (demo)",
    "budget_conscious": "Hafiz (demo)",
    "irregular_income": "Mei Ling (demo)",
}
PREFIX = {"frequent_bnpl": "fbnpl", "budget_conscious": "budget", "irregular_income": "irreg"}


def new_username(persona: str, token: Callable[[int], str] = secrets.token_hex) -> str:
    """`fbnpl-` plus 16 random hex characters: not guessable, still typeable."""
    return f"{PREFIX[persona]}-{token(8)}"


def as_csv(rows: list[dict[str, str]]) -> bytes:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


def _ok(response: httpx.Response, what: str) -> Any:
    if response.status_code >= 400:
        raise RuntimeError(f"{what}: HTTP {response.status_code} {response.text[:300]}")
    return response.json() if response.content else None


def login(client: httpx.Client, username: str, passphrase: str | None) -> dict[str, str]:
    body = {"username": username}
    if passphrase is not None:
        body["passphrase"] = passphrase
    token = _ok(client.post("/api/auth/login", json=body), "login")["access_token"]
    return {"Authorization": f"Bearer {token}"}


def load_persona(
    client: httpx.Client,
    auth: dict[str, str],
    rows: list[dict[str, str]],
    *,
    confirm_suggestions: bool = True,
) -> dict[str, Any]:
    """Import `rows` (persona CSV shape) and confirm detected recurring items; return a summary."""
    preview = _ok(
        client.post(
            "/api/import/csv",
            files={"file": ("persona.csv", as_csv(rows), "text/csv")},
            headers=auth,
        ),
        "import preview",
    )
    fresh = [
        {
            "date": r["date"],
            "amount_sen": r["amount_sen"],
            "type": r["type"],
            "category": r["category_guess"],
            "description": r["description"],
        }
        for r in preview["rows"]
        if not r["duplicate"]
    ]
    created = 0
    if fresh:
        created = _ok(
            client.post("/api/import/confirm", json={"rows": fresh}, headers=auth),
            "import confirm",
        )["created"]
    confirmed = 0
    if confirm_suggestions:
        for s in _ok(client.get("/api/recurring-items/suggestions", headers=auth), "suggestions"):
            body = {
                "kind": s["kind"],
                "name": s["display_name"],
                "match_text": s["name"],
                "amount_sen": s["amount_sen"],
                "cadence": s["cadence"],
                "anchor_date": s["anchor_date"],
                "origin": "detected",
            }
            _ok(client.post("/api/recurring-items", json=body, headers=auth), "recurring item")
            confirmed += 1
    forecast = _ok(client.get("/api/forecast", headers=auth), "forecast")
    return {
        "previewed": len(preview["rows"]),
        "skipped": len(preview["skipped"]),
        "duplicates": preview["duplicate_count"],
        "created": created,
        "recurring_confirmed": confirmed,
        "forecast_status": forecast["status"],
        "months_of_history": forecast["months_of_history"],
        "band": forecast["band"],
        "health_score": forecast["health_score"],
    }


def read_accounts(path: Path) -> dict[str, dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_accounts(path: Path, accounts: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(accounts, indent=2) + "\n", encoding="utf-8")


def run(
    db: Database,
    client: httpx.Client,
    *,
    session: date,
    accounts_file: Path,
    personas: list[str],
) -> dict[str, dict[str, Any]]:
    accounts = read_accounts(accounts_file)
    results: dict[str, dict[str, Any]] = {}
    for persona in personas:
        account = accounts.get(persona) or {"username": new_username(persona)}
        seed_user(db, username=account["username"], display_name=PERSONAS[persona], persona=persona)
        accounts[persona] = account
        write_accounts(accounts_file, accounts)  # saved before any import, so a rerun reuses it
        auth = login(client, account["username"], account.get("passphrase"))
        rows = shift_rows(read_rows(PERSONA_DIR / f"{persona}.csv"), session)
        results[persona] = load_persona(client, auth, rows)
    return results


def main() -> int:
    from app.core.settings import MissingSettingsError, load_settings
    from app.db.client import build_client

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--session", type=date.fromisoformat, default=None, help="default: today")
    parser.add_argument("--persona", choices=sorted(PERSONAS), action="append")
    args = parser.parse_args()
    try:
        settings = load_settings()
    except MissingSettingsError as err:
        print(err, file=sys.stderr)
        return 2
    from app.api.deps import malaysia_today

    with httpx.Client(base_url=args.api.rstrip("/"), timeout=120) as client:
        results = run(
            build_client(settings),
            client,
            session=args.session or malaysia_today(),
            accounts_file=ACCOUNTS_FILE,
            personas=args.persona or list(PERSONAS),
        )
    for persona, summary in results.items():  # usernames stay in the private file
        print(persona, json.dumps(summary))
    print(f"Accounts are in {ACCOUNTS_FILE.relative_to(ROOT)} (gitignored).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
