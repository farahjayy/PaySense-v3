import pytest


def item(**overrides):
    return {
        "kind": "income",
        "name": "Monthly allowance",
        "amount_sen": 80000,
        "cadence": "monthly",
        "anchor_date": "2026-01-01",
    } | overrides


def create(api, headers, **overrides):
    res = api.post("/api/recurring-items", json=item(**overrides), headers=headers)
    assert res.status_code == 201, res.text
    return res.json()


def test_create_returns_a_manual_active_item(api, amir):
    res = api.post("/api/recurring-items", json=item(), headers=amir)

    assert res.status_code == 201
    assert res.json() | {"id": "x"} == {
        "id": "x",
        "kind": "income",
        "name": "Monthly allowance",
        "amount_sen": 80000,
        "cadence": "monthly",
        "custom_interval_days": None,
        "anchor_date": "2026-01-01",
        "active": True,
        "origin": "manual",
    }


def test_custom_cadence_needs_an_interval(api, amir):
    ok = api.post(
        "/api/recurring-items", json=item(cadence="custom", custom_interval_days=10), headers=amir
    )
    missing = api.post("/api/recurring-items", json=item(cadence="custom"), headers=amir)

    assert ok.status_code == 201 and ok.json()["custom_interval_days"] == 10
    assert missing.status_code == 422
    assert "interval" in missing.json()["detail"]["message"]


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "gift"},
        {"name": ""},
        {"amount_sen": 0},
        {"amount_sen": 1.5},
        {"cadence": "daily"},
        {"anchor_date": "soon"},
    ],
)
def test_create_validates(api, amir, bad):
    res = api.post("/api/recurring-items", json=item(**bad), headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "validation_error"


def test_list_returns_the_callers_items_and_can_hide_inactive_ones(api, amir):
    keep = create(api, amir, name="Rent", kind="bill")
    paused = create(api, amir, name="Gym", kind="bill")
    api.patch(f"/api/recurring-items/{paused['id']}", json={"active": False}, headers=amir)

    everything = api.get("/api/recurring-items", headers=amir).json()
    active = api.get("/api/recurring-items?active_only=true", headers=amir).json()

    assert {i["id"] for i in everything} == {keep["id"], paused["id"]}
    assert [i["id"] for i in active] == [keep["id"]]


def test_patch_updates_and_revalidates_the_cadence(api, amir):
    created = create(api, amir, cadence="custom", custom_interval_days=10)

    weekly = api.patch(
        f"/api/recurring-items/{created['id']}", json={"cadence": "weekly"}, headers=amir
    )
    bad = api.patch(
        f"/api/recurring-items/{created['id']}", json={"cadence": "custom"}, headers=amir
    )

    assert weekly.status_code == 200
    assert weekly.json()["cadence"] == "weekly" and weekly.json()["custom_interval_days"] is None
    assert bad.status_code == 422


@pytest.mark.parametrize(
    "patch", [{"kind": "bill"}, {"origin": "detected"}, {"user_id": "x"}, {"amount_sen": 0}]
)
def test_patch_rejects_what_it_does_not_own(api, amir, patch):
    created = create(api, amir)

    res = api.patch(f"/api/recurring-items/{created['id']}", json=patch, headers=amir)

    assert res.status_code == 422


def test_delete(api, amir):
    created = create(api, amir)

    assert api.delete(f"/api/recurring-items/{created['id']}", headers=amir).status_code == 204
    assert api.get("/api/recurring-items", headers=amir).json() == []
    assert api.delete(f"/api/recurring-items/{created['id']}", headers=amir).status_code == 404


def test_items_are_private_to_each_user(api, amir, siti):
    created = create(api, amir)

    assert api.get("/api/recurring-items", headers=siti).json() == []
    patched = api.patch(
        f"/api/recurring-items/{created['id']}", json={"name": "Hijacked"}, headers=siti
    )
    deleted = api.delete(f"/api/recurring-items/{created['id']}", headers=siti)
    assert patched.status_code == deleted.status_code == 404
    assert patched.json()["detail"]["code"] == "recurring_item_not_found"
    assert api.get("/api/recurring-items", headers=amir).json()[0]["name"] == "Monthly allowance"


def test_a_malformed_id_is_a_404(api, amir):
    assert (
        api.patch("/api/recurring-items/nope", json={"active": False}, headers=amir).status_code
        == 404
    )
    assert api.delete("/api/recurring-items/nope", headers=amir).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/recurring-items"),
        ("post", "/api/recurring-items"),
        ("patch", "/api/recurring-items/x"),
        ("delete", "/api/recurring-items/x"),
    ],
)
def test_every_route_requires_login(api, method, path):
    assert getattr(api, method)(path).status_code == 401
