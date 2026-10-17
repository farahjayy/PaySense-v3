"""WP4a / D-48: the model can never run a write, and can never name a user."""

import pytest

from app.assistant import executor, policy
from app.assistant.tools import MODEL_TOOLS, Tool
from app.assistant.writes import WRITE_FUNCTIONS


def test_no_write_is_reachable_from_the_model_registry():
    assert set(MODEL_TOOLS).isdisjoint(WRITE_FUNCTIONS)
    for name in ("add_transaction", "confirm_import", "create_plan", "set_budget", "delete_budget"):
        assert name in WRITE_FUNCTIONS
        assert name not in MODEL_TOOLS


@pytest.mark.parametrize("name", ["create_plan", "set_budget", "add_transaction", "delete_budget"])
def test_the_model_asking_for_a_write_is_refused(make_ctx, db, name):
    record = executor.run_tool(make_ctx("amir"), name, {}, caller="model")
    assert record.step.status == "refused"
    assert db.rows("bnpl_plans") == [] and db.rows("budgets") == []


def test_a_tier_two_tool_registered_by_mistake_still_cannot_run(make_ctx, monkeypatch):
    ran = []
    rogue = Tool(
        name="rogue_write",
        tier=2,
        description="A write that was registered in the wrong place by mistake.",
        input_model=MODEL_TOOLS["get_forecast"].input_model,
        handler=lambda ctx, args: ran.append(1),
        card_title="x",
    )
    monkeypatch.setitem(MODEL_TOOLS, "rogue_write", rogue)
    for caller in ("model", "guided"):
        record = executor.run_tool(make_ctx("amir"), "rogue_write", {}, caller=caller)
        assert record.step.status == "refused"
    assert ran == []


def test_policy_limits_by_caller():
    assert policy.max_tier("model") == 1
    assert policy.max_tier("guided") == 1
    with pytest.raises(ValueError):
        policy.max_tier("confirm")  # writes never go through the tool executor


@pytest.mark.parametrize(
    "args",
    [
        {"user_id": "00000000-0000-0000-0000-000000000000"},
        {"month": "2025-11", "USER_ID": "x"},
        {"filters": {"nested": {"user_id": "x"}}},
        {"items": [{"userId": "x"}]},
    ],
)
def test_any_user_id_in_the_arguments_is_refused(make_ctx, args):
    record = executor.run_tool(make_ctx("amir"), "get_spending_by_category", args, caller="model")
    assert record.step.status == "refused"
    assert "user" in record.step.summary.lower()
