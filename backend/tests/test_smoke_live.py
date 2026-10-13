"""The deployment smoke script, run against the real app on the in-memory database."""

import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.e2e_server import E2E_ORIGIN, E2E_USERNAME, build_e2e_app

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "smoke_live.py"
spec = importlib.util.spec_from_file_location("smoke_live", SCRIPT)
smoke = importlib.util.module_from_spec(spec)
spec.loader.exec_module(smoke)


@pytest.fixture
def client():
    return TestClient(build_e2e_app())


def test_a_healthy_deployment_passes_every_check(client):
    results = smoke.run_smoke(client, username=E2E_USERNAME, origin=E2E_ORIGIN)
    assert [r.name for r in results if not r.ok] == []
    assert len(results) == 7


def test_a_wrong_cors_origin_is_reported_with_the_fix(client):
    results = smoke.run_smoke(client, username=E2E_USERNAME, origin="https://other.example")
    failed = {r.name: r.detail for r in results if not r.ok}
    assert list(failed) == ["CORS allows the app's origin"]
    assert "CORS_ORIGINS" in failed["CORS allows the app's origin"]


def test_an_unseeded_username_stops_after_the_login_check(client):
    results = smoke.run_smoke(client, username="nobody", origin=E2E_ORIGIN)
    assert results[-1].name == "tester can log in"
    assert not results[-1].ok
    assert "seeded" in results[-1].detail


def test_an_unreachable_service_is_a_failed_check_not_a_traceback():
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    with httpx.Client(transport=httpx.MockTransport(refuse), base_url="http://x") as c:
        results = smoke.run_smoke(c, username="u", origin="http://o")
    assert not results[0].ok
    assert "request failed" in results[0].detail


def test_a_page_that_is_not_json_is_a_failed_check_not_a_crash():
    html = httpx.MockTransport(
        lambda request: httpx.Response(200, text="<html>Render is waking</html>")
    )
    with httpx.Client(transport=html, base_url="https://x.example") as client:
        results = smoke.run_smoke(client, username="a", origin="https://app.example")
    assert not results[0].ok and "unexpected response" in results[0].detail


def test_a_trailing_slash_on_the_origin_is_not_a_false_failure(client):
    results = smoke.run_smoke(client, username=E2E_USERNAME, origin=E2E_ORIGIN + "/")
    assert [r.name for r in results if not r.ok] == []


def test_main_exits_one_when_a_check_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        smoke.sys,
        "argv",
        ["smoke", "--api", "http://127.0.0.1:9", "--origin", "http://o", "--username", "a"],
    )
    assert smoke.main() == 1
    assert "FAIL" in capsys.readouterr().out
