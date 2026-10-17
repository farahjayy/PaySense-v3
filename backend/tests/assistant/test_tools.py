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
