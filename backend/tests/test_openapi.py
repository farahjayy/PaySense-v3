"""The OpenAPI document is the contract the frontend types are generated from (ADR D-18)."""

import pytest


@pytest.fixture
def spec(client):
    return client.get("/openapi.json").json()


def test_operation_ids_are_plain_function_names(spec):
    ids = {op["operationId"] for path in spec["paths"].values() for op in path.values()}

    assert ids == {"health", "login", "me"}


def test_response_fields_the_server_always_sends_are_required(spec):
    schemas = spec["components"]["schemas"]

    assert "persona" in schemas["UserOut"]["required"]
    assert "token_type" in schemas["LoginResponse"]["required"]


def test_error_responses_are_documented_with_the_envelope(spec):
    login = spec["paths"]["/api/auth/login"]["post"]["responses"]

    for status in ("401", "422", "429"):
        ref = login[status]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ErrorEnvelope")
    assert spec["paths"]["/api/auth/me"]["get"]["responses"]["401"]


def test_health_has_a_named_response_model(spec):
    ref = spec["paths"]["/api/health"]["get"]["responses"]["200"]["content"]["application/json"]
    assert ref["schema"]["$ref"].endswith("/HealthOut")
