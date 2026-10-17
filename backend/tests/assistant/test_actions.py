"""WP4b (ADR D-48): proposals, single-use confirmation, decline and the audit log."""

import datetime as dt

import pytest

from app.assistant import executor
from tests.assistant.conftest import load_persona, uid

TXN = {"date": "2025-12-20", "amount_sen": 1250, "type": "expense", "category": "Food",
       "description": "Nasi lemak"}  # fmt: skip
PHONE = {"provider": "spaylater", "item_name": "Phone", "purchase_date": "2025-12-29",
         "num_installments": 3, "total_price_sen": 79900}  # fmt: skip


def propose(ctx, type_, payload):
    return executor.run_tool(ctx, "propose_action", {"type": type_, "payload": payload},
                             caller="model")  # fmt: skip


def actions(db):
    return db.rows("assistant_actions")


# ------------------------------------------------------------------ propose
def test_a_proposal_is_stored_validated_and_writes_nothing(db, make_ctx):
    record = propose(make_ctx("amir"), "add_transaction", TXN)
    assert record.step.status == "ok" and record.step.tier == 1
    (row,) = actions(db)
    assert row["status"] == "pending" and row["type"] == "add_transaction"
    assert row["summary"] == "Add expense of RM 12.50 in Food on 20 Dec 2025 (Nasi lemak)."
    assert record.pending_action.payload.amount_sen == 1250
    assert db.rows("transactions") == []
    kinds = [e["kind"] for e in db.rows("assistant_events")]
    assert kinds == ["proposal"]


def test_an_identical_pending_proposal_is_reused(db, make_ctx):
    ctx = make_ctx("amir")
    first = propose(ctx, "add_transaction", TXN)
    second = propose(ctx, "add_transaction", dict(reversed(list(TXN.items()))))
    assert first.pending_action.id == second.pending_action.id
    assert len(actions(db)) == 1


@pytest.mark.parametrize(
    ("type_", "payload", "status"),
    [
        ("add_transaction", TXN | {"amount_sen": 12.5}, "error"),
        ("add_transaction", TXN | {"surprise": 1}, "error"),
        ("set_budget", {"category": "Refund", "limit_sen": 100}, "error"),
        ("delete_budget", {"category": "Food"}, "error"),  # no such budget
        ("create_plan", PHONE | {"num_installments": 0}, "error"),
        ("create_plan", PHONE | {"purchase_date": "2031-01-01"}, "error"),
        ("confirm_import", {"rows": [TXN]}, "error"),  # only the paste parser may propose this
        ("add_transaction", TXN | {"user_id": "someone"}, "refused"),
    ],
)
def test_bad_proposals_are_refused_and_nothing_is_stored(db, make_ctx, type_, payload, status):
    record = propose(make_ctx("amir"), type_, payload)
    assert record.step.status == status
    assert actions(db) == []


def test_a_plan_proposal_carries_the_servers_preview(db, make_ctx):
    load_persona(db, uid(db, "amir"))
    record = propose(make_ctx("amir"), "create_plan", PHONE)
    action = record.pending_action
    assert action.type == "create_plan"
    assert action.preview.total_price_sen == 79900 and len(action.preview.installments) == 3
    assert "SPayLater plan for Phone" in action.summary


# ------------------------------------------------------------------ confirm through the API
def _propose_via_api(api, headers, type_, payload, fake_db, username="amir"):
    from app.api.assistant import tool_context  # noqa: F401  (the route builds the same context)
    from app.assistant.actions import propose as store
    from app.assistant.context import ToolContext

    user = next(u for u in fake_db.rows("users") if u["username"] == username)
    ctx = ToolContext(db=fake_db, user_id=user["id"], today=dt.date(2025, 12, 29),
                      settings=api.app.state.settings, predictor=None)  # fmt: skip
    return store(ctx, type_, payload)


def test_confirm_runs_the_write_once_and_audits_it(api, amir, fake_db):
    row = _propose_via_api(api, amir, "add_transaction", TXN, fake_db)
    res = api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "confirmed" and body["transaction"]["amount_sen"] == 1250
    assert len(fake_db.rows("transactions")) == 1
    again = api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "action_not_pending"
    assert len(fake_db.rows("transactions")) == 1
    kinds = [e["kind"] for e in fake_db.rows("assistant_events")]
    assert kinds == ["proposal", "confirm", "refusal"]


def test_a_budget_is_set_and_deleted_through_confirmed_proposals(api, amir, fake_db):
    row = _propose_via_api(api, amir, "set_budget", {"category": "food", "limit_sen": 40000},
                           fake_db)  # fmt: skip
    assert row["payload"]["category"] == "Food"
    res = api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir)
    assert res.json()["budget"]["limit_sen"] == 40000
    row = _propose_via_api(api, amir, "delete_budget", {"category": "Food"}, fake_db)
    assert api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir).status_code == 200
    assert fake_db.rows("budgets") == []


def test_another_user_cannot_see_confirm_or_decline_a_proposal(api, amir, siti, fake_db):
    row = _propose_via_api(api, amir, "add_transaction", TXN, fake_db)
    for method in ("confirm", "decline"):
        res = api.post(f"/api/assistant/actions/{row['id']}/{method}", headers=siti)
        assert res.status_code == 404
    assert api.get(f"/api/assistant/actions/{row['id']}", headers=siti).status_code == 404
    assert fake_db.rows("transactions") == []
    assert actions(fake_db)[0]["status"] == "pending"


def test_an_expired_proposal_cannot_be_confirmed(api, amir, fake_db):
    row = _propose_via_api(api, amir, "add_transaction", TXN, fake_db)
    actions(fake_db)[0]["expires_at"] = (
        dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
    ).isoformat()
    res = api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir)
    assert res.status_code == 410 and res.json()["detail"]["code"] == "action_expired"
    assert actions(fake_db)[0]["status"] == "expired"
    assert fake_db.rows("transactions") == []


def test_a_tampered_payload_is_refused(api, amir, fake_db):
    row = _propose_via_api(api, amir, "add_transaction", TXN, fake_db)
    actions(fake_db)[0]["payload"]["amount_sen"] = 999_999  # changed after the person saw it
    res = api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir)
    assert res.status_code == 422 and res.json()["detail"]["code"] == "action_tampered"
    assert actions(fake_db)[0]["status"] == "failed"
    assert fake_db.rows("transactions") == []


def test_the_same_change_confirmed_twice_in_two_minutes_is_a_duplicate(api, amir, fake_db):
    first = _propose_via_api(api, amir, "add_transaction", TXN, fake_db)
    assert (
        api.post(f"/api/assistant/actions/{first['id']}/confirm", headers=amir).status_code == 200
    )
    second = _propose_via_api(api, amir, "add_transaction", TXN, fake_db)
    res = api.post(f"/api/assistant/actions/{second['id']}/confirm", headers=amir)
    assert res.status_code == 409 and res.json()["detail"]["code"] == "duplicate_confirm"
    assert len(fake_db.rows("transactions")) == 1


def test_a_write_that_fails_marks_the_proposal_failed(api, amir, fake_db, monkeypatch):
    from app.db import transactions as txn_repo

    row = _propose_via_api(api, amir, "add_transaction", TXN, fake_db)
    monkeypatch.setattr(txn_repo, "MAX_LEDGER_ROWS", 0)
    res = api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir)
    assert res.status_code == 413
    assert actions(fake_db)[0]["status"] == "failed"
    assert fake_db.rows("assistant_events")[-1]["status"] == "failed"


def test_decline_is_single_use_and_writes_nothing(api, amir, fake_db):
    row = _propose_via_api(api, amir, "add_transaction", TXN, fake_db)
    res = api.post(f"/api/assistant/actions/{row['id']}/decline", headers=amir)
    assert res.status_code == 200 and res.json()["status"] == "declined"
    assert api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir).status_code == 409
    assert api.post(f"/api/assistant/actions/{row['id']}/decline", headers=amir).status_code == 409
    assert fake_db.rows("transactions") == []


def test_the_card_comes_from_the_stored_payload(api, amir, fake_db):
    row = _propose_via_api(api, amir, "add_transaction", TXN, fake_db)
    card = api.get(f"/api/assistant/actions/{row['id']}", headers=amir).json()
    assert card["type"] == "add_transaction" and card["payload"]["amount_sen"] == 1250
    assert card["summary"] == row["summary"]


@pytest.mark.parametrize("path", ["confirm", "decline"])
def test_action_routes_need_a_session(api, path):
    url = "/api/assistant/actions/00000000-0000-0000-0000-000000000000/" + path
    assert api.post(url).status_code == 401


def test_a_malformed_action_id_is_simply_not_found(api, amir):
    assert api.post("/api/assistant/actions/not-a-uuid/confirm", headers=amir).status_code == 404


def test_a_confirmed_plan_runs_the_risk_confirm_path(api, amir, fake_db):
    from app.api.deps import get_today
    from tests.e2e_server import StubModel

    api.app.state.predictor = StubModel()
    api.app.dependency_overrides[get_today] = lambda: dt.date(2025, 12, 29)
    amir_id = next(u for u in fake_db.rows("users") if u["username"] == "amir")["id"]
    load_persona(fake_db, amir_id)
    row = _propose_via_api(api, amir, "create_plan", PHONE, fake_db)
    res = api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["plan"]["plan"]["item_name"] == "Phone"
    assert body["plan"]["check_id"] == fake_db.rows("risk_checks")[0]["id"]
    assert fake_db.rows("bnpl_plans")[0]["risk_check_id"] == body["plan"]["check_id"]


def test_without_the_risk_model_a_plan_proposal_fails_cleanly(api, amir, fake_db):
    from app.api.deps import get_today

    api.app.dependency_overrides[get_today] = lambda: dt.date(2025, 12, 29)
    row = _propose_via_api(api, amir, "create_plan", PHONE, fake_db)
    res = api.post(f"/api/assistant/actions/{row['id']}/confirm", headers=amir)
    assert res.status_code == 503
    assert actions(fake_db)[0]["status"] == "failed"
    assert fake_db.rows("bnpl_plans") == []
