"""The assessment pipeline wiring: what is passed to the search."""

import app.engines.risk.assess as assess_module
from app.engines.forecasting.models import MovingAverage
from app.engines.risk.assess import assess, next_income
from app.engines.risk.check import RiskRequest
from tests.engines.test_check import StubPredictor
from tests.engines.test_summary import EXISTING, ITEMS, TODAY, ledger


def run(limits, predictor=None, **kw):
    return assess(
        ledger(), ITEMS, EXISTING, limits,
        RiskRequest("spaylater", "Laptop", TODAY, 3, total_price_sen=60000),
        TODAY, MovingAverage(8), predictor or StubPredictor(0.5), seed=3, paths=150, **kw,
    )  # fmt: skip


def test_only_providers_with_a_recorded_limit_are_offered_as_a_switch(monkeypatch):
    seen = {}
    real = assess_module.search

    def spy(*args, **kwargs):
        seen.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(assess_module, "search", spy)
    run({"spaylater": 300000, "atome": 100000, "tiktok_paylater": None})

    assert set(seen["switch_to"]) == {"atome"}  # spaylater is the current one; None is not recorded


def test_with_no_recorded_limits_no_switch_is_offered(monkeypatch):
    seen = {}
    real = assess_module.search
    monkeypatch.setattr(assess_module, "search", lambda *a, **k: (seen.update(k), real(*a, **k))[1])
    run({})
    assert set(seen["switch_to"]) == set()


def test_the_next_income_is_the_soonest_confirmed_income_after_today():
    assert next_income(ITEMS, TODAY) == __import__("datetime").date(2025, 6, 1)
    assert next_income([i for i in ITEMS if i["kind"] == "bill"], TODAY) is None


def test_the_wait_horizon_stays_inside_the_purchase_date_window_the_api_accepts():
    from datetime import timedelta

    from app.api.risk import DAYS_AHEAD
    from app.engines.risk.assess import NEXT_INCOME_LOOKAHEAD_DAYS

    assert NEXT_INCOME_LOOKAHEAD_DAYS + 1 <= DAYS_AHEAD
    assert timedelta(days=NEXT_INCOME_LOOKAHEAD_DAYS) < timedelta(days=DAYS_AHEAD)
