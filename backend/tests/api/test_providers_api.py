import re

import pytest

NAMED = ["spaylater", "tiktok_paylater", "atome"]


# ------------------------------------------------------------------ providers
def test_providers_are_served_with_their_rules(api, amir):
    res = api.get("/api/providers", headers=amir)

    assert res.status_code == 200
    by_key = {p["key"]: p for p in res.json()}
    assert list(by_key) == ["spaylater", "tiktok_paylater", "atome", "other"]
    assert by_key["spaylater"]["start_offset_months"] == 1
    assert by_key["atome"]["checkout_instalments"] == 1
    assert by_key["other"]["rule_driven"] is False
    assert by_key["atome"]["label"] == "Atome"


def test_providers_require_login(api):
    res = api.get("/api/providers")

    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "not_authenticated"


# ------------------------------------------------------------------ limits
def test_limits_start_empty_for_every_named_provider(api, amir):
    res = api.get("/api/provider-limits", headers=amir)

    assert res.status_code == 200
    assert [r["provider"] for r in res.json()] == NAMED
    assert all(r["limit_sen"] is None and r["remaining_sen"] is None for r in res.json())
    assert all(r["used_sen"] == 0 for r in res.json())


def test_putting_a_limit_sets_it_and_reports_what_is_left(api, amir):
    res = api.put("/api/provider-limits/spaylater", json={"limit_sen": 250000}, headers=amir)

    assert res.status_code == 200
    assert res.json() == {
        "provider": "spaylater",
        "limit_sen": 250000,
        "used_sen": 0,
        "remaining_sen": 250000,
    }
    listed = {r["provider"]: r for r in api.get("/api/provider-limits", headers=amir).json()}
    assert listed["spaylater"]["limit_sen"] == 250000


def test_putting_again_replaces_the_limit(api, amir):
    api.put("/api/provider-limits/atome", json={"limit_sen": 10000}, headers=amir)

    res = api.put("/api/provider-limits/atome", json={"limit_sen": 40000}, headers=amir)

    assert res.json()["limit_sen"] == 40000


def test_deleting_a_limit_removes_it(api, amir):
    api.put("/api/provider-limits/atome", json={"limit_sen": 10000}, headers=amir)

    res = api.delete("/api/provider-limits/atome", headers=amir)

    assert res.status_code == 204
    listed = {r["provider"]: r for r in api.get("/api/provider-limits", headers=amir).json()}
    assert listed["atome"]["limit_sen"] is None
    assert api.delete("/api/provider-limits/atome", headers=amir).status_code == 404


@pytest.mark.parametrize("body", [{"limit_sen": 0}, {"limit_sen": -5}, {"limit_sen": 100.5}, {}])
def test_a_limit_must_be_a_positive_whole_number_of_sen(api, amir, body):
    res = api.put("/api/provider-limits/atome", json=body, headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "validation_error"


@pytest.mark.parametrize("provider", ["other", "grab_paylater"])
def test_only_the_named_providers_take_a_limit(api, amir, provider):
    res = api.put(f"/api/provider-limits/{provider}", json={"limit_sen": 1000}, headers=amir)

    assert res.status_code == 422


def test_limits_are_private_to_each_user(api, amir, siti):
    api.put("/api/provider-limits/spaylater", json={"limit_sen": 250000}, headers=amir)

    theirs = {r["provider"]: r for r in api.get("/api/provider-limits", headers=siti).json()}
    assert theirs["spaylater"]["limit_sen"] is None
    assert api.delete("/api/provider-limits/spaylater", headers=siti).status_code == 404
    mine = {r["provider"]: r for r in api.get("/api/provider-limits", headers=amir).json()}
    assert mine["spaylater"]["limit_sen"] == 250000


def test_limit_routes_require_login(api):
    assert api.get("/api/provider-limits").status_code == 401
    assert api.put("/api/provider-limits/atome", json={"limit_sen": 1}).status_code == 401
    assert api.delete("/api/provider-limits/atome").status_code == 401


# ------------------------------------------------------------------ the money contract (ADR D-29)
MONEY_NAME = re.compile(
    r"(amount|price|limit|payable|balance|margin|income|spend|net|total|upfront|financed)"
)


def _walk_properties(spec):
    for name, schema in spec["components"]["schemas"].items():
        for prop, definition in schema.get("properties", {}).items():
            yield name, prop, definition


def _types(definition):
    """The JSON types of a property; a list of numbers is judged by what its items are."""
    options = definition.get("anyOf", [definition])
    found = set()
    for option in options:
        if option.get("type") == "array":
            found |= _types(option.get("items", {}))
        else:
            found.add(option.get("type"))
    return found - {"null", None}


def test_every_money_field_in_the_api_is_an_integer_number_of_sen(api):
    spec = api.get("/openapi.json").json()
    checked = []

    for schema, prop, definition in _walk_properties(spec):
        if prop.endswith("_sen"):
            checked.append((schema, prop))
            assert _types(definition) <= {"integer"}, f"{schema}.{prop} must be an integer"
        elif MONEY_NAME.search(prop) and "number" in _types(definition):
            pytest.fail(f"{schema}.{prop} looks like money but is a float; use an integer *_sen")

    assert ("LimitOut", "limit_sen") in checked
