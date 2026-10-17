"""GET/PUT /api/settings (WP16, ADR D-50): the savings buffer, user-scoped, needs a session."""

import pytest


def test_settings_start_with_no_buffer(api, amir):
    res = api.get("/api/settings", headers=amir)
    assert res.status_code == 200
    assert res.json() == {"savings_buffer_sen": 0, "onboarding_state": "new"}


def test_setting_the_buffer_is_kept_and_only_for_the_caller(api, amir, siti):
    res = api.put("/api/settings", json={"savings_buffer_sen": 250_000}, headers=amir)
    assert res.status_code == 200
    assert res.json()["savings_buffer_sen"] == 250_000
    assert api.get("/api/settings", headers=amir).json()["savings_buffer_sen"] == 250_000
    assert api.get("/api/settings", headers=siti).json()["savings_buffer_sen"] == 0


def test_zero_clears_the_buffer(api, amir):
    api.put("/api/settings", json={"savings_buffer_sen": 1000}, headers=amir)
    res = api.put("/api/settings", json={"savings_buffer_sen": 0}, headers=amir)
    assert res.json()["savings_buffer_sen"] == 0


@pytest.mark.parametrize("bad", [-1, 10.5, "100", None, 100_000_000_001])
def test_a_bad_buffer_is_a_validation_error(api, amir, bad):
    res = api.put("/api/settings", json={"savings_buffer_sen": bad}, headers=amir)
    assert res.status_code == 422


def test_unknown_fields_are_refused(api, amir):
    res = api.put("/api/settings", json={"savings_buffer_sen": 1, "user_id": "x"}, headers=amir)
    assert res.status_code == 422


@pytest.mark.parametrize("method", ["get", "put"])
def test_settings_need_a_session(api, method):
    res = api.request(method.upper(), "/api/settings", json={"savings_buffer_sen": 1})
    assert res.status_code == 401


def test_the_buffer_reaches_the_forecast(api, amir, monkeypatch):
    """The dashboard forecast passes the caller's stored buffer to Engine 1 (the engine's use of
    it is tested in the engine tests)."""
    from app.api import forecast as forecast_api

    seen = {}
    real = forecast_api.build_forecast

    def spy(**kwargs):
        seen.update(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(forecast_api, "build_forecast", spy)
    api.put("/api/settings", json={"savings_buffer_sen": 123_400}, headers=amir)
    api.get("/api/forecast", headers=amir)
    assert seen["savings_buffer_sen"] == 123_400


def test_the_buffer_reaches_the_risk_check(api, amir, monkeypatch):
    from app.api import risk as risk_api

    seen = {}

    def spy(*args, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(risk_api, "assess", spy)
    api.app.state.predictor = object()
    api.put("/api/settings", json={"savings_buffer_sen": 77_700}, headers=amir)
    body = {"provider": "spaylater", "item_name": "Phone", "purchase_date": "2026-01-05",
            "num_installments": 3, "total_price_sen": 60_000}  # fmt: skip
    from datetime import date

    from app.api.deps import get_today

    api.app.dependency_overrides[get_today] = lambda: date(2026, 1, 5)
    with pytest.raises(RuntimeError, match="stop here"):
        api.post("/api/risk/check", json=body, headers=amir)
    assert seen["savings_buffer_sen"] == 77_700
