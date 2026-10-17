"""Find the demo scenarios by running the real risk model through the running API (WP1, WP16).

    cd backend && uv run python scripts/find_demo_scenario.py --api http://localhost:8000
    cd backend && uv run python scripts/find_demo_scenario.py --in-memory

`--in-memory` runs the same grid on an in-memory API with the served model and the personas
loaded by `load_personas.py` (no database or running server needed).

Logs in as the persona accounts in `data/private/persona_accounts.json` (made by
`load_personas.py`), runs a small grid of risk checks through `POST /api/risk/check` (stateless:
nothing is stored), and writes every request and response to
`evidence/demo-scenario/scenarios.json` and a readable summary to
`refdocs/fintechathon-2026/demo-scenario.md`. Nothing here is chosen by hand: the summary only
reports what the model returned, including when no purchase reaches Safe.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[2]
ACCOUNTS_FILE = ROOT / "data" / "private" / "persona_accounts.json"
EVIDENCE_FILE = ROOT / "evidence" / "demo-scenario" / "scenarios.json"
SUMMARY_FILE = ROOT / "refdocs" / "fintechathon-2026" / "demo-scenario.md"
MAX_WAITS = 6


@dataclass(frozen=True)
class Probe:
    persona: str
    label: str
    request: dict[str, Any]
    buffer_sen: int = 0  # a savings buffer the tester enters first (D-50); 0 = none


def phone(price_rm: int, today: date, provider: str = "spaylater", months: int = 3) -> dict:
    return {
        "provider": provider,
        "item_name": "Phone",
        "purchase_date": today.isoformat(),
        "num_installments": months,
        "total_price_sen": price_rm * 100,
    }


def default_grid(today: date) -> list[Probe]:
    """The story in work-packages.md section 6: an RM600-800 phone on SPayLater over 3 months for
    the frequent BNPL user, and small purchases for the budget-conscious contrast."""
    probes = [
        Probe("frequent_bnpl", f"Phone RM{p}, SPayLater, 3 months", phone(p, today))
        for p in (600, 650, 700, 750, 799)
    ]
    probes += [
        Probe(
            "budget_conscious",
            f"Headphones RM{p}, SPayLater, 3 months",
            {**phone(p, today), "item_name": "Headphones"},
        )
        for p in (30, 60, 120)
    ]
    probes += [
        Probe(
            "irregular_income",
            "Phone RM799, SPayLater, 3 months",
            phone(799, today),
        )
    ]
    # WP16 (D-50): the same phone after the tester enters savings they could fall back on
    probes += [
        Probe(
            persona,
            f"Phone RM799, SPayLater, 3 months, savings buffer RM{rm:,} entered",
            phone(799, today),
            buffer_sen=rm * 100,
        )
        for persona in ("frequent_bnpl", "irregular_income")
        for rm in (500, 1000, 2000)
    ]
    return probes


def post_check(
    client: httpx.Client,
    auth: dict[str, str],
    body: dict[str, Any],
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """POST a check, waiting out the per-user rate limit (Retry-After) rather than failing."""
    for _ in range(MAX_WAITS):
        response = client.post("/api/risk/check", json=body, headers=auth)
        if response.status_code not in (429, 503):
            return response
        sleep(float(response.headers.get("Retry-After", "6")))
    return response


def summarise(response: dict[str, Any]) -> dict[str, Any]:
    suggestion = response.get("suggestion") or {}
    return {
        "status": response["status"],
        "band": response.get("band"),
        "score": response.get("score"),
        "probability": response.get("probability"),
        "probability_without_purchase": response.get("probability_without_purchase"),
        "simulated_band": response.get("simulated_band"),
        "suggestion_status": suggestion.get("status"),
        "suggestion_changes": [c["label"] for c in suggestion.get("changes", [])],
        "suggestion_band": suggestion.get("band"),
        "top_factors": [f["text"] for f in response.get("factors", [])[:3]],
    }


def run_probes(
    client: httpx.Client,
    auths: dict[str, dict[str, str]],
    probes: list[Probe],
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    results = []
    buffered: set[str] = set()
    try:
        for probe in probes:
            auth = auths[probe.persona]
            if probe.buffer_sen or probe.persona in buffered:
                body = {"savings_buffer_sen": probe.buffer_sen}
                client.put("/api/settings", json=body, headers=auth).raise_for_status()
                buffered.add(probe.persona)
            response = post_check(client, auth, probe.request, sleep)
            body = response.json()
            results.append(
                {
                    "persona": probe.persona,
                    "label": probe.label,
                    "request": probe.request,
                    "buffer_sen": probe.buffer_sen,
                    "http_status": response.status_code,
                    "summary": summarise(body) if response.status_code == 200 else None,
                    "response": body,
                }
            )
    finally:  # leave every account as it was found: no buffer
        for persona in buffered:
            client.put("/api/settings", json={"savings_buffer_sen": 0}, headers=auths[persona])
    return results


def _money(probability: float | None) -> str:
    return "-" if probability is None else f"{probability:.3f}"


def render_markdown(
    results: list[dict[str, Any]],
    run_date: date,
    model: str | None,
    where: str = "the API with the real database",
) -> str:
    safe = [r for r in results if r["summary"] and r["summary"]["band"] == "Safe"]
    reach = [r for r in results if r["summary"] and r["summary"]["suggestion_status"] == "found"]
    lines = [
        "# Demo scenarios (found by the real model)",
        "",
        "> Generated by `backend/scripts/find_demo_scenario.py`; do not edit by hand. Full requests"
        " and responses: `evidence/demo-scenario/scenarios.json`.",
        f"> Run on {run_date.isoformat()} against {where} and the served"
        f" risk model (`{model or 'unknown'}`). The persona ledgers are shifted to end just before"
        " the run date, so the figures move a little from one run to the next.",
        "",
        "| Persona | Purchase | Band | Score | P(shortfall) | Without purchase | Smallest change |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in results:
        s = r["summary"]
        if s is None:
            lines.append(f"| {r['persona']} | {r['label']} | HTTP {r['http_status']} | | | | |")
            continue
        change = "; ".join(s["suggestion_changes"]) or "-"
        if s["suggestion_status"] == "none_found":
            change = "none reaches Safe"
        elif s["suggestion_status"] == "found":
            change = f"{change} -> {s['suggestion_band']}"
        lines.append(
            f"| {r['persona']} | {r['label']} | {s['band'] or s['status']} | {s['score']} | "
            f"{_money(s['probability'])} | {_money(s['probability_without_purchase'])} | {change} |"
        )
    lines += ["", "## What this means for the demo script", ""]
    if safe:
        lines.append(
            "- Purchases that come back **Safe**: "
            + ", ".join(f"{r['persona']} / {r['label']}" for r in safe)
            + "."
        )
    else:
        lines.append("- **No purchase in this grid comes back Safe.**")
    if safe and all(r.get("buffer_sen") for r in safe):
        lines.append("- **Without a savings buffer, no purchase in this grid comes back Safe.**")
    if reach:
        lines.append(
            "- A smallest change that reaches Safe exists for: "
            + ", ".join(f"{r['persona']} / {r['label']}" for r in reach)
            + "."
        )
    else:
        lines.append(
            "- **No smallest change reaches Safe** for any purchase in this grid; the demo says so"
            " honestly (step 2 of the demo script) rather than inventing one."
        )
    lines.append("")
    return "\n".join(lines)


IN_MEMORY = (
    "an in-memory API (the synthetic personas loaded by `load_personas.py`; migrations 0003-0006"
    " are not yet applied to the real database)"
)


def run_in_memory(today: date) -> list[dict[str, Any]]:
    import tempfile

    from fastapi.testclient import TestClient
    from load_personas import PERSONAS, login, read_accounts
    from load_personas import run as load

    from app.core.settings import Settings
    from app.engines.risk.artefact import load_if_present
    from app.main import create_app
    from tests.fakes import FakeSupabase

    settings = Settings(
        _env_file=None,
        supabase_url="https://demo.invalid",
        supabase_service_key="not-used-in-memory",
        session_secret="d" * 48,
        cors_origins="http://localhost:3000",
    )
    db = FakeSupabase()
    app = create_app(settings, db=db, predictor=load_if_present())
    with tempfile.TemporaryDirectory() as tmp, TestClient(app) as client:
        accounts_file = Path(tmp) / "accounts.json"  # throwaway passphrases, never kept
        load(db, client, session=today, accounts_file=accounts_file, personas=sorted(PERSONAS))
        accounts = read_accounts(accounts_file)
        auths = {p: login(client, a["username"], a["passphrase"]) for p, a in accounts.items()}
        return run_probes(client, auths, default_grid(today))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument("--in-memory", action="store_true", help="no server or database needed")
    parser.add_argument("--today", type=date.fromisoformat, default=None)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.path.insert(0, str(ROOT / "backend"))
    from load_personas import login

    from app.api.deps import malaysia_today

    today = args.today or malaysia_today()
    if args.in_memory:
        results, where = run_in_memory(today), IN_MEMORY
    else:
        if not ACCOUNTS_FILE.exists():
            print("Run scripts/load_personas.py first.", file=sys.stderr)
            return 2
        accounts = json.loads(ACCOUNTS_FILE.read_text(encoding="utf-8"))
        with httpx.Client(base_url=args.api.rstrip("/"), timeout=120) as client:
            auths = {
                p: login(client, a["username"], a.get("passphrase")) for p, a in accounts.items()
            }
            results = run_probes(client, auths, default_grid(today))
        where = "the API with the real database"
    versions = [r["response"].get("versions") for r in results if r["summary"]]
    model = next((v["model"] for v in versions if v), None)
    EVIDENCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_FILE.write_text(
        json.dumps({"run_date": today.isoformat(), "results": results}, indent=1) + "\n",
        encoding="utf-8",
    )
    SUMMARY_FILE.write_text(render_markdown(results, today, model, where), encoding="utf-8")
    for r in results:
        print(r["persona"], r["label"], json.dumps(r["summary"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
