"""WP-API: the contract for the competition features exists before they are built, so the
frontend can be written against generated types. Every new route needs a session."""

import pytest

NEW_ROUTES = [
    ("get", "/api/budgets"),
    ("put", "/api/budgets"),
    ("delete", "/api/budgets"),
    ("get", "/api/budgets/status"),
    ("post", "/api/budgets/suggest"),
    ("get", "/api/insights/bills"),
    ("get", "/api/insights/spending"),
    ("get", "/api/recommendations"),
    ("get", "/api/alerts"),
    ("get", "/api/assistant/status"),
    ("get", "/api/assistant/opening"),
    ("post", "/api/assistant/chat"),
    ("post", "/api/assistant/run"),
    ("get", "/api/assistant/actions/{action_id}"),
    ("post", "/api/assistant/actions/{action_id}/confirm"),
    ("post", "/api/assistant/actions/{action_id}/decline"),
]


@pytest.fixture
def spec(api):
    return api.get("/openapi.json").json()


@pytest.mark.parametrize(("method", "path"), NEW_ROUTES)
def test_every_new_route_is_in_the_contract(spec, method, path):
    assert method in spec["paths"][path]


@pytest.mark.parametrize(("method", "path"), NEW_ROUTES)
def test_every_new_route_refuses_a_visitor_without_a_session(api, method, path):
    url = path.replace("{action_id}", "00000000-0000-0000-0000-000000000000")
    res = api.request(method.upper(), url, params={"month": "2026-01", "category": "Food"})
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "not_authenticated"


def test_cards_and_pending_actions_are_typed_unions(spec):
    schemas = spec["components"]["schemas"]
    chat = schemas["ChatOut"]["properties"]
    card_refs = {c["$ref"].rsplit("/", 1)[-1] for c in chat["cards"]["items"]["oneOf"]}
    assert {"RiskCard", "BudgetStatusCard", "PastePreviewCard", "BillAnalysisCard"} <= card_refs
    action_refs = {a["$ref"].rsplit("/", 1)[-1] for a in chat["pending_actions"]["items"]["oneOf"]}
    assert action_refs == {
        "AddTransactionAction",
        "ConfirmImportAction",
        "CreatePlanAction",
        "SetBudgetAction",
        "DeleteBudgetAction",
    }


def test_chat_history_is_plain_text_only(spec):
    """Tool results are never accepted from the client (work-packages 3.3)."""
    schemas = spec["components"]["schemas"]
    assert set(schemas["ChatTurnIn"]["properties"]) == {"role", "text"}
    assert schemas["ChatTurnIn"]["additionalProperties"] is False


def test_no_request_model_lets_the_client_name_a_user(spec):
    schemas = spec["components"]["schemas"]
    for name in ("ChatIn", "RunToolIn", "BudgetIn", "BudgetSuggestIn", "BudgetDeleteIn"):
        assert "user_id" not in schemas[name]["properties"], name
