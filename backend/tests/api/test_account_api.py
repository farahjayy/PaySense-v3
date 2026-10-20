"""WP19: the privacy notice, export my data, delete my data."""

import pytest

from app.db.account import USER_TABLES
from tests.assistant.conftest import load_persona
from tests.fakes import FOREIGN_KEYS, HAS_CREATED_AT, NO_ID_TABLES, TEST_PASSPHRASE

DELETE = {"confirmation": "delete my data", "passphrase": TEST_PASSPHRASE}


def ids(fake_db, name):
    return next(u for u in fake_db.rows("users") if u["username"] == name)["id"]


@pytest.fixture
def both_have_everything(api, amir, siti, fake_db):
    """Every user-owned table gets at least one row for each user, through the real routes."""
    for headers, name in ((amir, "amir"), (siti, "siti")):
        load_persona(fake_db, ids(fake_db, name))
        assert api.post("/api/plans", headers=headers, json={
            "provider": "atome", "item_name": "Shoes", "purchase_date": "2026-01-05",
            "num_installments": 3, "total_price_sen": 18000}).status_code == 201  # fmt: skip
        api.put("/api/budgets", json={"category": "Food", "limit_sen": 1000}, headers=headers)
        api.post("/api/categories", json={"name": "Gym"}, headers=headers)
        api.put("/api/provider-limits/atome", json={"limit_sen": 150000}, headers=headers)
        api.post("/api/recurring-items", headers=headers, json={
            "kind": "bill", "name": "Gym", "amount_sen": 5000, "cadence": "monthly",
            "anchor_date": "2026-01-02"})  # fmt: skip
        import datetime as dt

        from app.db import assistant_actions, assistant_events, auth_events, risk_checks

        uid = ids(fake_db, name)
        assistant_actions.create(fake_db, uid, type="set_budget",
                                 payload={"category": "Food", "limit_sen": 1}, digest="a" * 64,
                                 summary="x", expires_at=dt.datetime.now(dt.UTC))  # fmt: skip
        assistant_events.record(fake_db, uid, "message", detail={"text": "hi"})
        auth_events.record(fake_db, "login", user_id=uid, email=f"{name}@example.com")
        risk_checks.create(fake_db, uid, {
            "input": {}, "features": {}, "feature_schema_hash": "h", "model_version": "v",
            "p": 0.1, "p_simulated": 0.1, "score": 90, "label": "safe", "factors": [],
            "counterfactuals": None, "repayment_flag": None, "curves": None})  # fmt: skip
        fake_db.rows("user_locks").append({"user_id": uid, "name": "plan_create",
                                           "acquired_at": "2026-01-01T00:00:00+00:00"})  # fmt: skip


def owned(fake_db, table, uid):
    return [r for r in fake_db.rows(table) if r.get("user_id") == uid]


def test_the_table_list_covers_every_user_owned_table():
    known = set(HAS_CREATED_AT) | NO_ID_TABLES | set(FOREIGN_KEYS) - {"users"}
    owned_tables = known - {"users", "user_settings"}
    assert owned_tables <= set(USER_TABLES)


def test_delete_removes_every_row_of_mine_in_every_table_and_none_of_theirs(
    api, amir, fake_db, both_have_everything
):
    amir_id, siti_id = ids(fake_db, "amir"), ids(fake_db, "siti")
    for table in USER_TABLES:
        assert owned(fake_db, table, amir_id), f"setup left {table} empty"
    before = {t: len(owned(fake_db, t, siti_id)) for t in USER_TABLES}
    res = api.post("/api/account/delete", json=DELETE, headers=amir)
    assert res.status_code == 200, res.text
    for table in USER_TABLES:
        assert owned(fake_db, table, amir_id) == [], table
        assert len(owned(fake_db, table, siti_id)) == before[table], table
    assert api.get("/api/auth/me", headers=amir).status_code == 200  # the account stays
    assert res.json()["deleted"]["transactions"] > 100


def test_delete_needs_the_phrase_and_the_passphrase(api, amir):
    wrong_phrase = {"confirmation": "delete", "passphrase": TEST_PASSPHRASE}
    assert api.post("/api/account/delete", json=wrong_phrase, headers=amir).status_code == 422
    no_passphrase = {"confirmation": "delete my data"}  # optional in the schema for Google (D-69)
    assert api.post("/api/account/delete", json=no_passphrase, headers=amir).status_code == 403


def test_a_wrong_passphrase_deletes_nothing(api, amir, fake_db, both_have_everything):
    wrong = {"confirmation": "delete my data", "passphrase": "wrong passphrase"}
    res = api.post("/api/account/delete", headers=amir, json=wrong)
    assert res.status_code == 403
    assert owned(fake_db, "transactions", ids(fake_db, "amir"))


def test_export_holds_every_table_and_no_secrets(api, amir, fake_db, both_have_everything):
    body = api.post("/api/account/export", headers=amir).json()
    assert set(body["tables"]) == set(USER_TABLES)
    assert all(body["tables"][t] for t in USER_TABLES if t != "user_locks")
    assert "passphrase_hash" not in body["user"] and "token_version" not in body["user"]
    siti_id = ids(fake_db, "siti")
    assert siti_id not in str(body)


def test_consent_is_versioned_and_names_the_provider(api, amir, fake_db):
    body = api.get("/api/account/consent", headers=amir).json()
    assert body["accepted"] is True and body["version"] == "v2"
    assert any("Groq" in s["text"] for s in body["sections"])
    row = next(r for r in fake_db.rows("user_settings") if r["user_id"] == ids(fake_db, "amir"))
    row["consent_version"] = None
    assert api.get("/api/account/consent", headers=amir).json()["accepted"] is False
    assert api.post("/api/account/consent", json={"version": "v1"}, headers=amir).status_code == 409
    assert api.post("/api/account/consent", json={"version": "v2"}, headers=amir).json()["accepted"]


def test_the_assistant_will_not_call_the_model_before_consent(api, amir, fake_db):
    from app.assistant.llm import FakeLLM, say

    row = next(r for r in fake_db.rows("user_settings") if r["user_id"] == ids(fake_db, "amir"))
    row["consent_version"] = None
    model = FakeLLM([say("hello")])
    api.app.state.llm = model
    res = api.post("/api/assistant/chat", json={"message": "hi"}, headers=amir)
    assert res.status_code == 403 and res.json()["detail"]["code"] == "consent_required"
    assert model.calls == []
    guided = api.post("/api/assistant/run", json={"tool": "get_budgets"}, headers=amir)
    assert guided.status_code == 200


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/api/account/consent"), ("post", "/api/account/consent"),
     ("post", "/api/account/export"), ("post", "/api/account/delete")],
)  # fmt: skip
def test_account_routes_need_a_session(api, method, path):
    assert api.request(method.upper(), path, json={}).status_code == 401


def test_delete_also_clears_the_savings_buffer(api, amir):
    """D-50's buffer is the user's data too: delete resets it to none."""
    assert api.put("/api/settings", json={"savings_buffer_sen": 50000}, headers=amir).is_success
    assert api.post("/api/account/delete", json=DELETE, headers=amir).is_success
    assert api.get("/api/settings", headers=amir).json()["savings_buffer_sen"] == 0
