"""POST /api/assistant/run (guided mode): the same tools, no model, user from the session."""

import pytest


def test_guided_mode_runs_a_read_tool_and_returns_its_card(api, amir):
    res = api.post("/api/assistant/run", json={"tool": "get_budgets"}, headers=amir)
    assert res.status_code == 200
    body = res.json()
    assert body["mode"] == "guided"
    assert body["steps"][0]["tool"] == "get_budgets" and body["steps"][0]["tier"] == 0
    assert body["cards"][0]["kind"] == "budgets"
    assert body["reply"] == body["steps"][0]["summary"]


def test_guided_mode_cannot_run_a_write(api, amir, fake_db):
    payload = {"category": "Food", "limit_sen": 1000}
    res = api.post(
        "/api/assistant/run", json={"tool": "set_budget", "arguments": payload}, headers=amir
    )
    assert res.status_code == 200
    assert res.json()["steps"][0]["status"] == "refused"
    assert res.json()["refused"] is True
    assert fake_db.rows("budgets") == []


def test_guided_mode_refuses_a_user_id_argument(api, amir, siti):
    siti_id = api.get("/api/auth/me", headers=siti).json()["id"]
    res = api.post(
        "/api/assistant/run",
        json={"tool": "get_budgets", "arguments": {"user_id": siti_id}},
        headers=amir,
    )
    assert res.json()["steps"][0]["status"] == "refused"


def test_guided_mode_only_sees_the_callers_data(api, amir, siti):
    api.put("/api/budgets", json={"category": "Food", "limit_sen": 4321}, headers=amir)
    res = api.post("/api/assistant/run", json={"tool": "get_budgets"}, headers=siti)
    assert res.json()["cards"][0]["data"]["budgets"] == []


@pytest.mark.parametrize("bad", [{"tool": "Get Budgets"}, {"tool": ""}, {"tool": "x" * 61}])
def test_a_malformed_tool_name_is_a_validation_error(api, amir, bad):
    assert api.post("/api/assistant/run", json=bad, headers=amir).status_code == 422


def test_guided_mode_needs_a_session(api):
    assert api.post("/api/assistant/run", json={"tool": "get_budgets"}).status_code == 401
