"""The Playwright backend's assistant switch: `E2E_FAKE_LLM=1` gives a scripted model to every
tester but the guided ones, and the assistant accounts start with the persona ledger."""

import pytest
from fastapi.testclient import TestClient

from tests.e2e_server import E2E_PASSPHRASE, build_e2e_app


def login(client: TestClient, username: str) -> dict[str, str]:
    res = client.post("/api/auth/login", json={"username": username, "passphrase": E2E_PASSPHRASE})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def fake_llm_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("E2E_FAKE_LLM", "1")
    return TestClient(build_e2e_app())


def test_without_the_switch_every_tester_is_in_guided_mode(monkeypatch):
    monkeypatch.delenv("E2E_FAKE_LLM", raising=False)
    client = TestClient(build_e2e_app())
    status = client.get("/api/assistant/status", headers=login(client, "e2e-desktop-assistant-llm"))
    assert status.json()["mode"] == "guided"


def test_the_guided_testers_stay_guided_with_the_switch_on(fake_llm_client):
    headers = login(fake_llm_client, "e2e-phone-assistant-guided")
    assert fake_llm_client.get("/api/assistant/status", headers=headers).json()["mode"] == "guided"


def test_the_scripted_model_checks_proposes_and_the_user_confirms(fake_llm_client):
    client = fake_llm_client
    headers = login(client, "e2e-desktop-assistant-llm")
    assert client.get("/api/assistant/status", headers=headers).json()["mode"] == "llm"

    first = client.post(
        "/api/assistant/chat",
        json={"message": "Can I afford an RM799 phone on SPayLater over 3 months?"},
        headers=headers,
    ).json()
    assert [s["tool"] for s in first["steps"]] == ["check_purchase_risk"]
    assert first["cards"][0]["kind"] == "risk"
    assert first["cards"][0]["data"]["status"] == "ok"  # the persona ledger unlocks the check
    assert not first["narration_replaced"]

    second = client.post(
        "/api/assistant/chat", json={"message": "Yes, go ahead."}, headers=headers
    ).json()
    [action] = second["pending_actions"]
    assert action["type"] == "create_plan"
    assert action["payload"]["total_price_sen"] == 79900

    done = client.post(f"/api/assistant/actions/{action['id']}/confirm", headers=headers)
    assert done.status_code == 200, done.text
    plans = client.get("/api/plans", headers=headers).json()
    assert [p["item_name"] for p in plans] == ["Phone"]


def test_anything_else_gets_a_reply_with_no_figures(fake_llm_client):
    headers = login(fake_llm_client, "e2e-desktop-assistant-llm")
    out = fake_llm_client.post(
        "/api/assistant/chat", json={"message": "hello"}, headers=headers
    ).json()
    assert out["steps"] == [] and not any(ch.isdigit() for ch in out["reply"])
