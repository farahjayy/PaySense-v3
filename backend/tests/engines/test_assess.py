"""The assessment pipeline wiring: what is passed to the search."""

import datetime as dt

import app.engines.risk.assess as assess_module
from app.engines.forecasting.models import MovingAverage
from app.engines.risk.assess import assess, next_income
from app.engines.risk.check import RiskRequest
from tests.engines.test_check import StubPredictor
from tests.engines.test_summary import EXISTING, ITEMS, TODAY, ledger


def run(limits, predictor=None, paths=150):
    return assess(
        ledger(), ITEMS, EXISTING, limits,
        RiskRequest("spaylater", "Laptop", TODAY, 3, total_price_sen=60000),
        TODAY, MovingAverage(8), predictor or StubPredictor(0.5), seed=3, paths=paths,
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
    assert next_income(ITEMS, TODAY) == dt.date(2025, 6, 1)
    assert next_income([i for i in ITEMS if i["kind"] == "bill"], TODAY) is None


def test_the_wait_horizon_stays_inside_the_purchase_date_window_the_api_accepts():
    from datetime import timedelta

    from app.api.risk import DAYS_AHEAD
    from app.engines.risk.assess import NEXT_INCOME_LOOKAHEAD_DAYS

    assert timedelta(days=NEXT_INCOME_LOOKAHEAD_DAYS) < timedelta(days=DAYS_AHEAD)


def test_a_locked_ledger_gives_a_locked_result_with_no_reasons_and_no_suggestion():
    out = assess(
        [], ITEMS, EXISTING, {},
        RiskRequest("spaylater", "Laptop", TODAY, 3, total_price_sen=60000),
        TODAY, MovingAverage(8), StubPredictor(0.5), seed=3, paths=150,
    )  # fmt: skip
    assert out.result.status == "locked"
    assert out.factors == () and out.suggestion is None


def test_a_computed_result_carries_its_reasons_as_a_tuple():
    out = run({})
    assert out.result.status == "ok"
    assert isinstance(out.factors, tuple)


def test_candidates_are_screened_with_fewer_paths_but_never_more_than_the_full_run(monkeypatch):
    seen = []
    real = assess_module.run_check

    def spy(*args, **kwargs):
        seen.append(kwargs["paths"])
        return real(*args, **kwargs)

    monkeypatch.setattr(assess_module, "run_check", spy)
    run({}, paths=150)
    assert max(seen) == 150  # the screen is min(SCREEN_PATHS, 150): never above the full run
    seen.clear()
    run({}, paths=1000)
    assert assess_module.SCREEN_PATHS in seen and 1000 in seen
