"""Smoke-test a running PaySense API (local or deployed). Read-only apart from logging in.

    cd backend && uv run python scripts/smoke_live.py --api https://<service>.onrender.com \
        --origin https://<app>.vercel.app --username <a seeded tester>

The tester's passphrase is read from the SMOKE_PASSPHRASE environment variable (never a command
argument, so it stays out of shell history and process lists).

Checks, in order: the service answers, the browser's origin is allowed by CORS, an unauthenticated
call is refused, login works, the session is accepted, the provider rules load, and the forecast
route answers (locked is a valid answer for a tester with no history). Exits 1 if anything fails.
"""

import argparse
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_smoke(
    client: httpx.Client, *, username: str, origin: str, passphrase: str = ""
) -> list[Check]:
    results: list[Check] = []
    origin = origin.rstrip("/")

    def check(name: str, test: Callable[[], str | None]) -> bool:
        """Run one check; `test` returns None on success or a reason on failure."""
        try:
            problem = test()
        except httpx.HTTPError as err:
            problem = f"request failed: {err}"
        except (ValueError, KeyError, TypeError, AttributeError) as err:
            # e.g. a cold-start or wrong-URL HTML page that still answers 200
            problem = f"unexpected response: {err!r}"
        results.append(Check(name, problem is None, problem or "ok"))
        return problem is None

    def health() -> str | None:
        r = client.get("/api/health")
        return (
            None if r.status_code == 200 and r.json().get("status") == "ok" else f"{r.status_code}"
        )

    def cors() -> str | None:
        r = client.options(
            "/api/auth/login",
            headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
        )
        allowed = r.headers.get("access-control-allow-origin")
        return (
            None if allowed == origin else f"origin not allowed (got {allowed!r}); fix CORS_ORIGINS"
        )

    def refuses_anonymous() -> str | None:
        r = client.get("/api/forecast")
        return None if r.status_code == 401 else f"expected 401, got {r.status_code}"

    check("service answers /api/health", health)
    check("CORS allows the app's origin", cors)
    check("anonymous request is refused", refuses_anonymous)

    token: dict[str, str] = {}

    def login() -> str | None:
        r = client.post("/api/auth/login", json={"username": username, "passphrase": passphrase})
        if r.status_code != 200:
            return f"{r.status_code}: is {username!r} seeded, and is SMOKE_PASSPHRASE right?"
        token["value"] = r.json()["access_token"]
        return None

    if not check("tester can log in", login):
        return results
    auth = {"Authorization": f"Bearer {token['value']}"}

    def session() -> str | None:
        r = client.get("/api/auth/me", headers=auth)
        return None if r.status_code == 200 else f"{r.status_code}"

    def providers() -> str | None:
        r = client.get("/api/providers", headers=auth)
        if r.status_code != 200:
            return f"{r.status_code}"
        keys = {p["key"] for p in r.json()}
        return None if {"spaylater", "tiktok_paylater", "atome", "other"} <= keys else f"got {keys}"

    def forecast() -> str | None:
        r = client.get("/api/forecast", headers=auth)
        if r.status_code != 200:
            return f"{r.status_code}"
        return None if r.json().get("status") in ("ok", "locked") else "unexpected status field"

    check("session is accepted", session)
    check("provider rules load", providers)
    check("forecast route answers", forecast)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", required=True, help="API base URL, no trailing slash")
    parser.add_argument("--origin", required=True, help="the frontend origin the browser will use")
    parser.add_argument("--username", required=True)
    args = parser.parse_args()
    with httpx.Client(base_url=args.api.rstrip("/"), timeout=60) as client:
        results = run_smoke(
            client,
            username=args.username,
            origin=args.origin,
            passphrase=os.environ.get("SMOKE_PASSPHRASE", ""),
        )
    for r in results:
        print(f"{'PASS' if r.ok else 'FAIL'}  {r.name}" + ("" if r.ok else f"  -  {r.detail}"))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
