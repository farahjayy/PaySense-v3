"""WP6 scenario suite: the assistant's tasks end to end with a scripted model (deterministic).

Each test is one task from work-packages.md section 6, driven through the real HTTP routes, the
real tools and the in-memory database. The fake model only decides which tools to call and what
to say; every figure comes from the tools.
"""

from datetime import date

import pytest

from app.api.deps import get_today
from app.assistant.llm import FakeLLM, LLMError, call, say
from tests.assistant.conftest import load_persona
from tests.e2e_server import StubModel

TODAY = date(2025, 12, 29)
PHONE = {"provider": "spaylater", "item_name": "Phone", "purchase_date": "2025-12-29",
         "num_installments": 3, "total_price_sen": 79900}  # fmt: skip


@pytest.fixture
def user(api, amir, fake_db):
    api.app.dependency_overrides[get_today] = lambda: TODAY
    api.app.state.predictor = StubModel()
    amir_id = next(u for u in fake_db.rows("users") if u["username"] == "amir")["id"]
    load_persona(fake_db, amir_id)

    class Session:
        def say(self, script, message, **extra):
            api.app.state.llm = FakeLLM(script)
            res = api.post("/api/assistant/chat", json={"message": message, **extra}, headers=amir)
            assert res.status_code == 200, res.text
            return res.json()

        def confirm(self, action_id):
            return api.post(f"/api/assistant/actions/{action_id}/confirm", headers=amir)

    return Session()


def tool_data(messages, n=-1):
    return [m for m in messages if m.role == "tool"][n].tool_results[-1].content["data"]


def test_afford_then_safest_option_then_go_ahead_then_confirm(user, fake_db):
    # 1. can I afford it?
    def narrate(system, messages, tools):
        data = tool_data(messages)
        return say(f"It comes out {data['band']} with a score of {data['score']}.")

    first = user.say([call("check_purchase_risk", PHONE), narrate],
                     "Can I afford an RM799 phone on SPayLater over 3 months?")  # fmt: skip
    assert [s["tool"] for s in first["steps"]] == ["check_purchase_risk"]
    risk = first["cards"][0]["data"]
    assert risk["status"] == "ok" and risk["suggestion"]["status"] in (
        "found", "none_found", "already_safe"
    )  # fmt: skip

    # 2. the safest way: the model reads the suggestion from the same tool (history is text only)
    def safest(system, messages, tools):
        suggestion = tool_data(messages)["suggestion"]
        if suggestion["status"] == "found":
            return say(
                "The smallest change that makes it Safe: " + suggestion["changes"][0]["label"]
            )
        return say("No change I can check makes this purchase Safe right now.")

    second = user.say([call("check_purchase_risk", PHONE), safest],
                      "What's the safest way to buy it?")  # fmt: skip
    assert second["narration_replaced"] is False

    # 3. go ahead: a proposal, never a write
    third = user.say(
        [call("propose_action", {"type": "create_plan", "payload": PHONE}),
         say("I have prepared the plan. Press Confirm to add it.")],
        "Go ahead with that.",
    )  # fmt: skip
    (action,) = third["pending_actions"]
    assert action["type"] == "create_plan" and action["preview"]["total_price_sen"] == 79900
    assert fake_db.rows("bnpl_plans") == []

    # 4. the person confirms: the plan and its frozen report are saved, once
    done = user.confirm(action["id"])
    assert done.status_code == 200
    assert len(fake_db.rows("bnpl_plans")) == 1 and len(fake_db.rows("risk_checks")) == 1


def test_what_do_i_owe_this_month(user):
    body = user.say([call("get_bill_analysis"), call("get_bills_by_month", call_id="c2"),
                     say("Your bills and instalments for the next 30 days are on the cards.")],
                    "What do I owe this month?")  # fmt: skip
    assert [c["kind"] for c in body["cards"]] == ["bill_analysis", "bills"]


def test_how_am_i_doing(user):
    body = user.say([call("get_spending_insights", {"month": "2025-11"}),
                     call("get_recommendations", call_id="c2"),
                     say("November's spending and what to do next are on the cards.")],
                    "How am I doing?")  # fmt: skip
    assert [c["kind"] for c in body["cards"]] == ["spending_insights", "recommendations"]
    assert body["narration_replaced"] is False


def test_set_a_budget_and_confirm(user, fake_db):
    body = user.say(
        [call("propose_action", {"type": "set_budget",
                                 "payload": {"category": "Food", "limit_sen": 40000}}),
         say("Your RM 400.00 Food budget is waiting for your confirmation.")],
        "Set my food budget to RM400.",
    )  # fmt: skip
    (action,) = body["pending_actions"]
    assert user.confirm(action["id"]).json()["budget"]["limit_sen"] == 40000
    assert fake_db.rows("budgets")[0]["category"] == "Food"


def test_suggest_a_budget_stores_nothing(user, fake_db):
    body = user.say([call("suggest_budget"), say("Here is a suggested split.")],
                    "Suggest a budget.")  # fmt: skip
    assert body["cards"][0]["kind"] == "budget_suggestion"
    assert fake_db.rows("budgets") == []


def test_add_a_transaction_by_chat(user, fake_db):
    payload = {"date": "2025-12-29", "amount_sen": 1250, "type": "expense", "category": "Food",
               "description": "Nasi lemak"}  # fmt: skip
    before = len(fake_db.rows("transactions"))
    body = user.say([call("propose_action", {"type": "add_transaction", "payload": payload}),
                     say("Adding RM 12.50 for nasi lemak is waiting for your confirmation.")],
                    "I spent RM12.50 on nasi lemak today.")  # fmt: skip
    (action,) = body["pending_actions"]
    assert len(fake_db.rows("transactions")) == before
    assert user.confirm(action["id"]).status_code == 200
    assert len(fake_db.rows("transactions")) == before + 1


def test_import_by_chat(user, fake_db):
    pasted = "27/12 Grab ride RM15.00\n28/12 Mamak 8.50"
    rows = [{"date": "2025-12-27", "amount_sen": 1500, "type": "expense"},
            {"date": "2025-12-28", "amount_sen": 850, "type": "expense"}]  # fmt: skip
    body = user.say([call("parse_pasted_transactions", {"rows": rows}),
                     say("I read 2 transactions. Press Confirm to add them.")],
                    "Add these", pasted_text=pasted)  # fmt: skip
    (action,) = body["pending_actions"]
    assert action["type"] == "confirm_import"
    assert user.confirm(action["id"]).json()["imported"]["created"] == 2


def test_an_ambiguous_request_gets_a_question(user):
    body = user.say([call("list_providers_and_limits"),
                     say("Which provider and how many instalments would you like?")],
                    "Can I afford a phone?")  # fmt: skip
    assert body["reply"].endswith("?") and body["pending_actions"] == []


def test_an_out_of_scope_request_is_declined(user):
    body = user.say([say("OUT_OF_SCOPE")], "Who will win the football tonight?")
    assert body["refused"] is True


def test_the_model_being_down_falls_back_to_guided_mode(user):
    body = user.say([LLMError("the model's provider answered HTTP 503")], "How am I doing?")
    assert body["mode"] == "guided" and "guided mode" in body["reply"]
