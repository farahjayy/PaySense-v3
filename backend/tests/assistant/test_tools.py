"""WP4a: every assistant tool runs the same shared function as its screen and returns a card."""

import pytest

from app.assistant import executor
from app.assistant.tools import MODEL_TOOLS
from tests.assistant.conftest import load_persona, uid

READ_TOOLS = {
    "get_month_summary": ({}, "month_summary"),
    "get_spending_by_category": ({"month": "2025-11"}, "category_spending"),
    "list_recent_transactions": ({"limit": 5}, "transactions"),
    "get_bills_by_month": ({}, "bills"),
    "get_bill_analysis": ({}, "bill_analysis"),
    "get_spending_insights": ({"month": "2025-11"}, "spending_insights"),
    "get_forecast": ({}, "forecast"),
    "list_plans": ({}, "plans"),
    "list_providers_and_limits": ({}, "providers"),
    "get_budgets": ({}, "budgets"),
    "get_budget_status": ({}, "budget_status"),
    "get_recommendations": ({}, "recommendations"),
    "get_alerts": ({}, "alerts"),
}
PHONE = {
    "provider": "spaylater",
    "item_name": "Phone",
    "purchase_date": "2025-12-29",
    "num_installments": 3,
    "total_price_sen": 79900,
}
COMPUTE_TOOLS = {
    "check_purchase_risk": (PHONE, "risk"),
    "preview_plan": (PHONE, "plan_preview"),
    "suggest_budget": ({}, "budget_suggestion"),
    "find_safer_timing": (PHONE, "schedule"),
}


@pytest.fixture
def ctx(db, make_ctx):
    load_persona(db, uid(db, "amir"))
    return make_ctx("amir")


def test_the_registry_has_every_tool_with_its_tier():
    tiers = {t.name: t.tier for t in MODEL_TOOLS.values()}
    for name in READ_TOOLS:
        assert tiers[name] == 0, name
    for name in COMPUTE_TOOLS:
        assert tiers[name] == 1, name
    assert all(t.tier <= 1 for t in MODEL_TOOLS.values())


def test_every_tool_has_a_description_and_a_json_schema():
    for tool in MODEL_TOOLS.values():
        assert len(tool.description) > 20, tool.name
        schema = tool.input_schema()
        assert schema["type"] == "object"
        assert "user_id" not in schema.get("properties", {})


@pytest.mark.parametrize("name", sorted(READ_TOOLS | COMPUTE_TOOLS))
def test_each_tool_runs_and_returns_its_card(ctx, name):
    args, kind = (READ_TOOLS | COMPUTE_TOOLS)[name]
    record = executor.run_tool(ctx, name, args, caller="model")
    assert record.step.status == "ok", record.step.summary
    assert record.step.tier == MODEL_TOOLS[name].tier
    assert record.card is not None and record.card.kind == kind
    assert record.data is not None
    assert record.step.summary


def test_the_risk_tool_is_the_same_pipeline_as_the_route(ctx, make_ctx, settings, db):
    from fastapi.testclient import TestClient

    from app.api.deps import get_today
    from app.api.plans import PlanIn
    from app.api.risk import check_for
    from app.engines.forecasting.serving import served_forecaster
    from tests.assistant.conftest import TODAY

    record = executor.run_tool(ctx, "check_purchase_risk", PHONE, caller="model")
    direct = check_for(
        PlanIn.model_validate(PHONE), ctx.user_id, db, TODAY, served_forecaster(), ctx.predictor
    )
    assert record.card.data.model_dump() == direct.model_dump()
    assert TestClient and get_today  # the route calls check_for too (tests/api/test_risk_api.py)


def test_recent_transactions_are_bounded_and_can_hide_descriptions(ctx, settings):
    record = executor.run_tool(ctx, "list_recent_transactions", {"limit": 50}, caller="model")
    assert record.step.status == "error"  # over the cap of 20
    hidden = ctx.__class__(**{**ctx.__dict__, "settings": settings.model_copy(
        update={"assistant_redact_descriptions": True})})  # fmt: skip
    record = executor.run_tool(hidden, "list_recent_transactions", {"limit": 20}, caller="model")
    rows = record.card.data.transactions
    assert 0 < len(rows) <= 20
    assert all(r.description is None for r in rows)
    assert record.card.data.descriptions_redacted


def test_a_bad_purchase_is_an_error_step_not_an_exception(ctx):
    bad = PHONE | {"purchase_date": "2030-01-01"}
    record = executor.run_tool(ctx, "check_purchase_risk", bad, caller="model")
    assert record.step.status == "error"
    assert "purchase date" in record.step.summary.lower()


def test_no_risk_model_is_an_error_step(db, make_ctx):
    load_persona(db, uid(db, "amir"))
    ctx = make_ctx("amir")
    ctx = ctx.__class__(**{**ctx.__dict__, "predictor": None})
    record = executor.run_tool(ctx, "check_purchase_risk", PHONE, caller="model")
    assert record.step.status == "error"
    assert "not available" in record.step.summary.lower()


def test_unknown_tools_and_unknown_arguments_are_refused(ctx):
    assert executor.run_tool(ctx, "drop_tables", {}, caller="model").step.status == "refused"
    record = executor.run_tool(ctx, "get_forecast", {"verbose": True}, caller="model")
    assert record.step.status == "error"


def test_the_timing_tool_is_the_same_search_as_the_route(ctx, db):
    """D-57: `find_safer_timing` and POST /api/risk/schedule share `schedule_for`."""
    from app.api.plans import PlanIn
    from app.api.risk import schedule_for
    from app.engines.forecasting.serving import served_forecaster
    from tests.assistant.conftest import TODAY

    record = executor.run_tool(ctx, "find_safer_timing", PHONE, caller="model")
    direct = schedule_for(
        PlanIn.model_validate(PHONE), ctx.user_id, db, TODAY, served_forecaster(), ctx.predictor
    )
    assert record.card.data.model_dump() == direct.model_dump()
    assert "nothing saved" in record.step.summary.lower()


def test_the_risk_tool_tells_the_model_what_the_purchase_adds(ctx):
    """D-57: the second opinion reaches the model, so it can narrate with/without/added."""
    from app.assistant.agent import _model_view

    record = executor.run_tool(ctx, "check_purchase_risk", PHONE, caller="model")
    view = _model_view(record.data)
    opinion = view["second_opinion"]
    assert opinion is not None
    assert {"without_probability", "with_probability", "added_probability"} <= set(opinion)
    assert opinion["stack"] and opinion["exposure"]


def test_the_timing_tool_without_a_risk_model_is_an_error_step(db, make_ctx):
    load_persona(db, uid(db, "amir"))
    ctx = make_ctx("amir")
    ctx = ctx.__class__(**{**ctx.__dict__, "predictor": None})
    record = executor.run_tool(ctx, "find_safer_timing", PHONE, caller="model")
    assert record.step.status == "error"
    assert "not available" in record.step.summary.lower()


def test_the_model_sees_the_chosen_timing_even_when_the_list_is_cut(ctx, monkeypatch):
    """Review finding 2: the search stops at the chosen option, the last in a list the model's
    view may cut; the result names it separately."""
    from app.assistant.agent import MODEL_VIEW_LIST, _model_view

    record = executor.run_tool(ctx, "find_safer_timing", PHONE, caller="model")
    data = record.data
    data["options"] = [data["options"][0]] * (MODEL_VIEW_LIST + 3)
    view = _model_view(data)
    assert "chosen" in view and len(view["options"]) == MODEL_VIEW_LIST + 1


def test_the_timing_tool_shares_the_routes_rate_limit(ctx, monkeypatch):
    """Review finding 3: the tool calls the search directly, so it carries the limit itself."""
    from app.api.rate_limit import RequestRateLimiter
    from app.api.risk import SCHEDULES_PER_MINUTE
    from app.assistant import tools

    monkeypatch.setattr(tools, "_TIMING_LIMITER", RequestRateLimiter())
    steps = [executor.run_tool(ctx, "find_safer_timing", PHONE, caller="model").step
             for _ in range(SCHEDULES_PER_MINUTE + 1)]  # fmt: skip
    assert [s.status for s in steps[:-1]] == ["ok"] * SCHEDULES_PER_MINUTE
    assert steps[-1].status == "error" and "too often" in steps[-1].summary
