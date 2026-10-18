"""D-57: the Second-Opinion Check on POST /api/risk/check and POST /api/risk/schedule."""

import pytest

from tests.api import test_risk_api as risk

pinned = risk.pinned  # the stub model, the moving-average forecaster and the pinned day
TODAY, body, fill, user_id = risk.TODAY, risk.body, risk.fill, risk.user_id


@pytest.fixture
def ledger(fake_db):
    fill(fake_db, "amir")
    return fake_db


def test_the_check_returns_the_second_opinion_from_the_simulation(api, amir, ledger):
    res = api.post("/api/risk/check", json=body(), headers=amir)
    assert res.status_code == 200, res.text
    out = res.json()
    second = out["second_opinion"]
    assert second["without_probability"] == out["probability_without_purchase"]
    assert second["with_probability"] == out["simulated_probability"]
    expected = max(out["simulated_probability"] - out["probability_without_purchase"], 0)
    assert second["added_probability"] == pytest.approx(expected, abs=1e-6)
    assert second["already_at_risk"] == (out["probability_without_purchase"] >= 0.30)
    plan_months = sum(m["new_plan_sen"] for m in second["stack"])
    assert plan_months == out["plan"]["total_payable_sen"] - out["plan"]["cash_at_purchase_sen"]
    assert second["exposure"]["plans_after"] == second["exposure"]["plans_before"] + 1
    assert second["stack"][0]["month"] == TODAY.strftime("%Y-%m")


def test_existing_plans_from_every_provider_are_stacked(api, amir, ledger):
    # an Atome plan the student already has
    created = api.post("/api/plans", json=body(provider="atome", item_name="Shoes",
                                               total_price_sen=30000), headers=amir)  # fmt: skip
    assert created.status_code == 201, created.text
    second = api.post("/api/risk/check", json=body(), headers=amir).json()["second_opinion"]
    labels = {p["provider_label"] for m in second["stack"] for p in m["by_provider"]}
    assert "Atome" in labels
    assert "Atome" in second["exposure"]["providers_before"]
    assert second["exposure"]["unpaid_after_sen"] > second["exposure"]["unpaid_before_sen"]


def test_the_schedule_lists_the_options_tried_and_the_rule(api, amir, ledger):
    res = api.post("/api/risk/schedule", json=body(), headers=amir)
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["status"] == "ok" and out["added_max"] == 0.05 and out["at_risk_edge"] == 0.30
    first = out["options"][0]
    assert first["as_typed"] and first["purchase_date"] == TODAY.isoformat()
    for option in out["options"]:
        added = max(option["with_probability"] - out["without_probability"], 0)
        assert option["added_probability"] == pytest.approx(added, abs=1e-6)
        assert option["qualifies"] == (added <= 0.05 and option["with_probability"] < 0.30)
    chosen = out["chosen_index"]
    if chosen is not None:
        assert out["options"][chosen]["qualifies"]
        assert not any(o["qualifies"] for o in out["options"][:chosen])


def test_a_short_ledger_gives_a_locked_schedule(api, amir):
    out = api.post("/api/risk/schedule", json=body(), headers=amir).json()
    assert out["status"] == "locked" and out["options"] == [] and out["chosen_index"] is None


def test_the_schedule_is_only_for_the_signed_in_user(api, amir, siti, ledger):
    assert api.post("/api/risk/schedule", json=body()).status_code == 401
    # siti has no history: her schedule is locked, whatever amir's ledger holds
    assert api.post("/api/risk/schedule", json=body(), headers=siti).json()["status"] == "locked"


def test_the_schedule_is_rate_limited(api, amir, ledger):
    codes = [api.post("/api/risk/schedule", json=body(), headers=amir).status_code
             for _ in range(6)]  # fmt: skip
    assert codes[:5] == [200] * 5 and codes[5] == 429


def test_a_saved_report_keeps_the_second_opinion_it_was_decided_on(api, amir, ledger):
    """Going ahead freezes what the purchase added at that moment, like the band and score."""
    confirmed = api.post("/api/risk/confirm", json=body(), headers=amir)
    assert confirmed.status_code == 201, confirmed.text
    seen = confirmed.json()["check"]["second_opinion"]
    report = api.get(f"/api/risk/checks/{confirmed.json()['check_id']}", headers=amir).json()
    assert report["second_opinion"] == seen


def test_a_report_saved_before_the_second_opinion_still_reads(api, amir, ledger):
    confirmed = api.post("/api/risk/confirm", json=body(), headers=amir).json()
    row = next(r for r in ledger.rows("risk_checks") if r["id"] == confirmed["check_id"])
    row["input"].pop("second_opinion")
    report = api.get(f"/api/risk/checks/{confirmed['check_id']}", headers=amir).json()
    assert report["status"] == "ok" and report["second_opinion"] is None
