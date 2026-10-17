"""The demo-scenario finder (WP1): it only reports what the model returned."""

import importlib.util
import sys
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from tests.e2e_server import E2E_TODAY, build_e2e_app

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location(
    "find_demo_scenario", SCRIPTS / "find_demo_scenario.py"
)
finder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finder)
loader_spec = importlib.util.spec_from_file_location("load_personas", SCRIPTS / "load_personas.py")
loader = importlib.util.module_from_spec(loader_spec)
loader_spec.loader.exec_module(loader)


def test_the_grid_follows_the_demo_story():
    grid = finder.default_grid(E2E_TODAY)
    phones = [p for p in grid if p.persona == "frequent_bnpl"]
    assert [p.request["total_price_sen"] for p in phones] == [60000, 65000, 70000, 75000, 79900]
    assert all(p.request["provider"] == "spaylater" for p in grid)
    assert all(p.request["num_installments"] == 3 for p in grid)


def test_probes_run_through_the_api_and_are_summarised(tmp_path):
    app = build_e2e_app()
    with TestClient(app) as client:
        loader.run(
            app.state.db,
            client,
            session=E2E_TODAY,
            accounts_file=tmp_path / "a.json",
            personas=["frequent_bnpl"],
        )
        accounts = loader.read_accounts(tmp_path / "a.json")
        account = accounts["frequent_bnpl"]
        auth = loader.login(client, account["username"], account["passphrase"])
        probes = [p for p in finder.default_grid(E2E_TODAY) if p.persona == "frequent_bnpl"][:2]
        results = finder.run_probes(client, {"frequent_bnpl": auth}, probes, sleep=lambda _: None)
    assert [r["http_status"] for r in results] == [200, 200]
    assert all(r["summary"]["band"] in ("Safe", "Caution", "At Risk") for r in results)
    page = finder.render_markdown(results, E2E_TODAY, "e2e-stub")
    assert "find_demo_scenario.py" in page
    assert "Phone RM600" in page


def test_a_rate_limited_check_waits_and_retries():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "3"}, json={})
        return httpx.Response(200, json={"status": "locked"})

    waited = []
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="http://x") as client:
        response = finder.post_check(client, {}, {}, sleep=waited.append)
    assert response.status_code == 200
    assert waited == [3.0]


def test_no_safe_result_is_said_plainly():
    results = [
        {
            "persona": "frequent_bnpl",
            "label": "Phone RM799",
            "http_status": 200,
            "summary": {
                "status": "ok",
                "band": "At Risk",
                "score": 20,
                "probability": 0.8,
                "probability_without_purchase": 0.7,
                "simulated_band": "At Risk",
                "suggestion_status": "none_found",
                "suggestion_changes": [],
                "suggestion_band": None,
                "top_factors": [],
            },
        }
    ]
    page = finder.render_markdown(results, E2E_TODAY, "m")
    assert "No purchase in this grid comes back Safe" in page
    assert "No smallest change reaches Safe" in page
    assert "none reaches Safe" in page
