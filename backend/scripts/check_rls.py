"""Prove the public anon key can read nothing (migrations/README.md, P0 definition of done).

    cd backend && uv run python scripts/check_rls.py

Needs SUPABASE_URL and SUPABASE_ANON_KEY (the *publishable/anon* key, never the service key)
in backend/.env or the environment. For every table it sends a plain PostgREST read with the
anon key and passes only if the response is a permission error or an empty list.
"""

import os
import sys

import httpx
from dotenv import dotenv_values

TABLES = (
    "users",
    "user_settings",
    "recurring_items",
    "risk_checks",
    "bnpl_plans",
    "bnpl_installments",
    "transactions",
    "provider_limits",
    "user_categories",
    "user_locks",
)


def main() -> int:
    env = {**dotenv_values(".env"), **os.environ}
    url, anon = env.get("SUPABASE_URL"), env.get("SUPABASE_ANON_KEY")
    if not url or not anon:
        print(
            "Set SUPABASE_URL and SUPABASE_ANON_KEY (anon/publishable key) first.", file=sys.stderr
        )
        return 2
    failures = 0
    for table in TABLES:
        res = httpx.get(
            f"{url.rstrip('/')}/rest/v1/{table}",
            params={"select": "*", "limit": "1"},
            headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
            timeout=15,
        )
        leaked = res.status_code == 200 and res.json() != []
        denied = res.status_code in (401, 403) or (res.status_code == 200 and not leaked)
        print(f"{'PASS' if denied and not leaked else 'FAIL'}  {table:<18} HTTP {res.status_code}")
        failures += 0 if denied and not leaked else 1
    print("anon key reads nothing" if failures == 0 else f"{failures} table(s) readable by anon!")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
