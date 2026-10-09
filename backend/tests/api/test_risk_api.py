"""POST /api/risk/check, POST /api/risk/confirm, GET /api/risk/checks/{id}.

A stub model stands in for the trained one; the real pipeline (plan rules, both simulations,
features, repayment rule, counterfactual search, frozen report) runs underneath it.
"""

from datetime import date, timedelta

import pytest

from app.api.deps import get_today
from app.api.forecast import get_forecaster
from app.db import plans as plans_repo
from app.db import transactions as transactions_repo
from app.db import users
from app.engines.forecasting.models import MovingAverage
from app.engines.risk.features import FEATURE_NAMES, FEATURE_SCHEMA_HASH

TODAY = date(2025, 5, 12)  # a Monday
RATIO = FEATURE_NAMES.index("instalment_to_income")
DSR = FEATURE_NAMES.index("dsr_with_purchase")


class Model:
    """Risk = twice the instalment-to-income ratio, so longer plans and cheaper items help."""

    version = "stub-model-1"
    feature_schema_hash = FEATURE_SCHEMA_HASH

    def predict(self, vector):
        return min(1.0, vector[RATIO] * 2.0)

    def contributions(self, vector):
        out = [0.0] * len(FEATURE_NAMES)
        out[DSR] = 0.05  # one reason that clears the 0.02 bar
        out[RATIO] = 0.01  # and one that does not
        return out


@pytest.fixture(autouse=True)
def pinned(api):
    api.app.dependency_overrides[get_today] = lambda: TODAY
    api.app.dependency_overrides[get_forecaster] = lambda: MovingAverage(8)
    api.app.state.predictor = Model()
    yield
    api.app.dependency_overrides.clear()


def user_id(fake_db, username):
    return users.get_by_username(fake_db, username)["id"]


def txn(day, amount, kind="expense", category="Food", description="Kedai makan"):
    return {
        "date": day.isoformat(),
        "amount_sen": amount,
        "type": kind,
        "category": category,
        "description": description,
    }


def fill(fake_db, username, income=200000, weekly=6000, first=date(2025, 1, 6)):
    rows, day = [], first
    while day < TODAY:
        rows.append(txn(day, weekly))
        day += timedelta(days=7)
    rows += [
        txn(date(2025, m, 1), income, "income", "Allowance", "Duit belanja") for m in range(1, 6)
    ]
    transactions_repo.bulk_create(fake_db, user_id(fake_db, username), rows, source="seed")


def body(**overrides):
    base = {
        "provider": "spaylater",
        "item_name": "Headphones",
        "purchase_date": TODAY.isoformat(),
        "num_installments": 3,
        "total_price_sen": 60000,
    }
    base.update(overrides)
    return base


def test_all_three_routes_refuse_anonymous_requests(api):
    assert api.post("/api/risk/check", json=body()).status_code == 401
    assert api.post("/api/risk/confirm", json=body()).status_code == 401
    assert api.get("/api/risk/checks/00000000-0000-0000-0000-000000000000").status_code == 401


def test_without_a_loaded_model_the_check_is_unavailable_not_a_made_up_number(api, amir):
    api.app.state.predictor = None
    res = api.post("/api/risk/check", json=body(), headers=amir)

    assert res.status_code == 503
    assert res.json()["detail"]["code"] == "risk_check_unavailable"


def test_a_new_user_with_no_history_gets_a_refusal_and_no_number(api, amir):
    res = api.post("/api/risk/check", json=body(), headers=amir)

    assert res.status_code == 200
    out = res.json()
    assert out["status"] == "locked" and out["lock_reason"] in (
        "needs_four_months",
        "no_usable_history",
    )
    assert out["probability"] is None and out["band"] is None and out["factors"] == []
    assert out["plan"]["total_price_sen"] == 60000  # the schedule is still shown


def test_a_ledger_with_history_returns_the_whole_answer(api, amir, fake_db):
    fill(fake_db, "amir")
    res = api.post("/api/risk/check", json=body(total_price_sen=60000), headers=amir)

    assert res.status_code == 200
    out = res.json()
    assert out["status"] == "ok"
    assert 0 <= out["probability"] <= 1 and out["band"] in ("Safe", "Caution", "At Risk")
    assert out["score"] == round((1 - out["probability"]) * 100)
    assert out["simulated_probability"] >= out["probability_without_purchase"]
    assert [f["feature"] for f in out["factors"]] == ["dsr_with_purchase"]
    assert "%" in out["factors"][0]["text"]
    assert out["plan"]["num_installments"] == 3
    assert len(out["with_plan_curve"]["months"]) == len(out["without_curve"]["months"]) >= 3
    assert out["versions"] == {"model": "stub-model-1", "feature_schema_hash": FEATURE_SCHEMA_HASH}
    assert out["repayment"]["level"] == "none"
    assert out["check_id"] is None  # a check is stateless until the purchase is confirmed


@pytest.mark.parametrize(
    "bad",
    [
        {"num_installments": 0},
        {"num_installments": 99},
        {"total_price_sen": 12.5},
        {"total_price_sen": -1},
        {"item_name": "   "},
        {"surprise": 1},
    ],
)
def test_malformed_requests_get_the_standard_validation_envelope(api, amir, bad):
    res = api.post("/api/risk/check", json=body(**bad), headers=amir)
    assert res.status_code == 422


def test_a_request_the_plan_rules_reject_is_a_422_with_their_reason(api, amir, fake_db):
    fill(fake_db, "amir")
    res = api.post(
        "/api/risk/check",
        json=body(provider="other", total_price_sen=None, num_installments=3),
        headers=amir,
    )

    assert res.status_code == 422
    assert res.json()["detail"]["code"] in (
        "first_payment_date_required",
        "provider_label_required",
    )


def test_an_unaffordable_purchase_comes_with_the_smallest_change_that_reaches_safe(
    api, amir, fake_db
):
    fill(fake_db, "amir")  # RM2,000 a month
    res = api.post(
        "/api/risk/check",
        json=body(total_price_sen=120000, num_installments=2),
        headers=amir,
    )

    out = res.json()
    assert out["band"] != "Safe"
    suggestion = out["suggestion"]
    assert suggestion["status"] == "found"
    assert suggestion["changes"] and all(c["label"] for c in suggestion["changes"])
    assert suggestion["band"] == "Safe" and suggestion["probability"] < 0.10
    assert suggestion["request"]["item_name"] == "Headphones"


def test_a_purchase_that_is_already_safe_says_so_instead_of_suggesting_changes(api, amir, fake_db):
    fill(fake_db, "amir")
    out = api.post(
        "/api/risk/check", json=body(total_price_sen=6000, num_installments=3), headers=amir
    ).json()

    assert out["band"] == "Safe"
    assert out["suggestion"]["status"] == "already_safe" and out["suggestion"]["changes"] == []


def test_overdue_instalments_show_in_the_repayment_flag_without_changing_the_probability(
    api, amir, fake_db
):
    fill(fake_db, "amir")
    clean = api.post("/api/risk/check", json=body(), headers=amir).json()
    uid = user_id(fake_db, "amir")
    overdue = [
        {"seq": s, "due_date": date(2025, 2 + s, 1), "amount_sen": 5000, "is_paid": False}
        for s in (1, 2, 3)
    ]
    from app.domain.schedule import Instalment

    plans_repo.create_plan(
        fake_db,
        uid,
        {
            "item_name": "Old",
            "provider": "atome",
            "provider_label": "Atome",
            "schedule_source": "provider_rule",
            "total_price_sen": 15000,
            "financed_sen": 15000,
            "upfront_sen": 0,
            "monthly_fee_rate_pct": 0,
            "num_installments": 3,
            "purchase_date": date(2025, 2, 1),
            "first_payment_date": date(2025, 3, 1),
        },
        [Instalment(o["seq"], o["due_date"], o["amount_sen"], False) for o in overdue],
    )
    flagged = api.post("/api/risk/check", json=body(), headers=amir).json()

    assert flagged["repayment"]["level"] == "warning"
    assert flagged["repayment"]["overdue_count"] == 3
    assert "Bank Negara" in flagged["repayment"]["reason"]
    assert clean["repayment"]["level"] == "none"


def test_confirming_creates_exactly_one_plan_and_one_frozen_check_linked_together(
    api, amir, fake_db
):
    fill(fake_db, "amir")
    uid = user_id(fake_db, "amir")
    res = api.post("/api/risk/confirm", json=body(), headers=amir)

    assert res.status_code == 201
    out = res.json()
    plans = plans_repo.list_with_instalments(fake_db, uid)
    checks = fake_db.rows("risk_checks")
    assert len(plans) == 1 and len(checks) == 1
    assert plans[0]["risk_check_id"] == checks[0]["id"] == out["check_id"]
    assert plans[0]["risk_check_type"] == "before_purchase"
    assert plans[0]["risk_score_at_creation"] == checks[0]["score"] == out["check"]["score"]
    assert out["plan"]["item_name"] == "Headphones"


def test_the_frozen_report_reads_back_unchanged_after_the_ledger_changes(api, amir, fake_db):
    fill(fake_db, "amir")
    confirmed = api.post("/api/risk/confirm", json=body(), headers=amir).json()
    transactions_repo.bulk_create(
        fake_db,
        user_id(fake_db, "amir"),
        [txn(TODAY - timedelta(days=1), 90000, category="Shopping")],
        source="manual",
    )
    read = api.get(f"/api/risk/checks/{confirmed['check_id']}", headers=amir)

    assert read.status_code == 200
    frozen = read.json()
    for field in ("probability", "band", "score", "factors", "plan", "with_plan_curve", "versions"):
        assert frozen[field] == confirmed["check"][field], field
    assert frozen["check_id"] == confirmed["check_id"]


def test_another_user_cannot_read_a_frozen_check(api, amir, siti, fake_db):
    fill(fake_db, "amir")
    check_id = api.post("/api/risk/confirm", json=body(), headers=amir).json()["check_id"]

    assert api.get(f"/api/risk/checks/{check_id}", headers=siti).status_code == 404
    assert api.get("/api/risk/checks/not-a-uuid", headers=amir).status_code == 404


def test_a_failure_while_saving_the_plan_leaves_neither_a_plan_nor_a_check(
    api, amir, fake_db, monkeypatch
):
    fill(fake_db, "amir")

    def explode(*_args, **_kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr("app.api.risk.store_plan", explode)
    with pytest.raises(RuntimeError):
        api.post("/api/risk/confirm", json=body(), headers=amir)

    assert fake_db.rows("risk_checks") == []
    assert plans_repo.list_with_instalments(fake_db, user_id(fake_db, "amir")) == []


def test_confirming_with_a_locked_ledger_creates_nothing(api, amir, fake_db):
    res = api.post("/api/risk/confirm", json=body(), headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "forecast_locked"
    assert fake_db.rows("risk_checks") == []


def test_the_check_route_is_limited_per_user(api, amir, siti, fake_db):
    fill(fake_db, "amir")
    statuses = [
        api.post("/api/risk/check", json=body(), headers=amir).status_code for _ in range(11)
    ]
    assert statuses[:10] == [200] * 10 and statuses[10] == 429
    assert api.post("/api/risk/check", json=body(), headers=siti).status_code == 200


# --------------------------------------------------------------------- review follow-ups
def test_too_many_checks_at_once_are_turned_away_with_a_retry_hint_not_queued(
    api, amir, fake_db, monkeypatch
):
    import app.api.risk as risk_module

    fill(fake_db, "amir")
    held = [
        risk_module.ADMISSION.acquire(blocking=False) for _ in range(risk_module.MAX_CONCURRENT)
    ]
    assert all(held)
    try:
        res = api.post("/api/risk/check", json=body(), headers=amir)
        confirm = api.post("/api/risk/confirm", json=body(), headers=amir)
    finally:
        for _ in held:
            risk_module.ADMISSION.release()

    assert res.status_code == 503 and res.json()["detail"]["code"] == "risk_check_busy"
    assert int(res.headers["Retry-After"]) >= 1
    assert confirm.status_code == 503
    assert fake_db.rows("risk_checks") == []
    # and the slot comes back: the next request runs normally
    assert api.post("/api/risk/check", json=body(), headers=amir).status_code == 200


def test_a_failed_check_still_releases_its_slot(api, amir, fake_db):
    import app.api.risk as risk_module

    fill(fake_db, "amir")
    for _ in range(risk_module.MAX_CONCURRENT + 2):
        bad = api.post(
            "/api/risk/check", json=body(provider="other", total_price_sen=None), headers=amir
        )
        assert bad.status_code == 422
    assert api.post("/api/risk/check", json=body(), headers=amir).status_code == 200


def test_a_failing_cleanup_does_not_hide_the_real_error_or_stop_the_raise(
    api, amir, fake_db, monkeypatch
):
    fill(fake_db, "amir")

    def explode(*_a, **_k):
        raise RuntimeError("the plan could not be saved")

    def explode_too(*_a, **_k):
        raise OSError("and the cleanup failed too")

    monkeypatch.setattr("app.api.risk.store_plan", explode)
    monkeypatch.setattr("app.api.risk.risk_checks.delete", explode_too)
    with pytest.raises(RuntimeError, match="could not be saved"):
        api.post("/api/risk/confirm", json=body(), headers=amir)


def test_confirming_the_same_purchase_twice_in_a_row_does_not_create_a_second_plan(
    api, amir, fake_db
):
    fill(fake_db, "amir")
    first = api.post("/api/risk/confirm", json=body(), headers=amir)
    second = api.post("/api/risk/confirm", json=body(), headers=amir)

    assert first.status_code == 201
    assert second.status_code == 409 and second.json()["detail"]["code"] == "duplicate_confirm"
    assert len(plans_repo.list_with_instalments(fake_db, user_id(fake_db, "amir"))) == 1
    assert len(fake_db.rows("risk_checks")) == 1


def test_a_different_purchase_is_not_mistaken_for_a_duplicate(api, amir, fake_db):
    fill(fake_db, "amir")
    assert api.post("/api/risk/confirm", json=body(), headers=amir).status_code == 201
    other = api.post("/api/risk/confirm", json=body(item_name="Phone case"), headers=amir)
    assert other.status_code == 201


@pytest.mark.parametrize("days", [-60, 400, 3000])
def test_a_purchase_date_far_from_today_is_refused(api, amir, fake_db, days):
    fill(fake_db, "amir")
    far = (TODAY + timedelta(days=days)).isoformat()
    res = api.post("/api/risk/check", json=body(purchase_date=far), headers=amir)

    assert res.status_code == 422
    assert res.json()["detail"]["code"] == "purchase_date_out_of_range"


def test_dates_close_to_today_are_fine(api, amir, fake_db):
    fill(fake_db, "amir")
    for days in (-30, 0, 90):
        day = (TODAY + timedelta(days=days)).isoformat()
        assert (
            api.post("/api/risk/check", json=body(purchase_date=day), headers=amir).status_code
            == 200
        )


def test_the_confirm_response_and_the_saved_report_carry_the_same_rounded_numbers(
    api, amir, fake_db
):
    fill(fake_db, "amir")
    confirmed = api.post("/api/risk/confirm", json=body(), headers=amir).json()
    saved = api.get(f"/api/risk/checks/{confirmed['check_id']}", headers=amir).json()

    assert saved["probability"] == confirmed["check"]["probability"]
    assert saved["simulated_probability"] == confirmed["check"]["simulated_probability"]


def test_health_stays_up_while_the_risk_check_slots_are_taken(api):
    import app.api.risk as risk_module

    held = [
        risk_module.ADMISSION.acquire(blocking=False) for _ in range(risk_module.MAX_CONCURRENT)
    ]
    try:
        assert api.get("/api/health").status_code == 200
    finally:
        for _ in held:
            risk_module.ADMISSION.release()


def test_a_model_that_rounds_just_over_one_still_gives_a_valid_probability():
    from app.engines.risk.artefact import clamp_probability

    assert clamp_probability(1.0000001) == 1.0
    assert clamp_probability(-1e-9) == 0.0
    assert clamp_probability(0.37) == 0.37
