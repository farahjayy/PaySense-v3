"""Per-user limits on the expensive routes: one logged-in user cannot starve the others."""

import pytest

from app.api.forecast import get_forecaster
from app.api.rate_limit import RequestRateLimiter
from app.engines.forecasting.models import MovingAverage
from app.main import create_app


class TestRequestRateLimiter:
    def make(self):
        now = [0.0]
        return RequestRateLimiter(clock=lambda: now[0]), now

    def test_allows_up_to_the_limit_then_refuses_with_a_wait(self):
        limiter, now = self.make()
        for _ in range(3):
            assert limiter.allow("forecast:u1", max_requests=3, window_seconds=60) == (True, 0)
        allowed, retry_after = limiter.allow("forecast:u1", max_requests=3, window_seconds=60)
        assert not allowed
        assert retry_after == 60

        now[0] = 45
        assert limiter.allow("forecast:u1", max_requests=3, window_seconds=60) == (False, 15)

    def test_the_window_slides_so_old_requests_stop_counting(self):
        limiter, now = self.make()
        for _ in range(3):
            limiter.allow("k", 3, 60)
        now[0] = 61
        assert limiter.allow("k", 3, 60) == (True, 0)

    def test_keys_are_independent(self):
        limiter, _ = self.make()
        for _ in range(3):
            limiter.allow("forecast:u1", 3, 60)
        assert limiter.allow("forecast:u1", 3, 60)[0] is False
        assert limiter.allow("forecast:u2", 3, 60)[0] is True
        assert limiter.allow("import:u1", 3, 60)[0] is True

    def test_refused_requests_do_not_extend_the_block(self):
        limiter, now = self.make()
        for _ in range(3):
            limiter.allow("k", 3, 60)
        for second in range(1, 30):
            now[0] = second
            limiter.allow("k", 3, 60)  # hammering while blocked
        now[0] = 61
        assert limiter.allow("k", 3, 60)[0] is True

    def test_memory_is_bounded_by_a_key_cap(self):
        limiter = RequestRateLimiter(max_keys=100, clock=lambda: 0.0)
        for i in range(500):
            limiter.allow(f"k{i}", 5, 60)
        assert limiter.tracked_keys() <= 100


@pytest.fixture
def limited(api):
    api.app.dependency_overrides[get_forecaster] = lambda: MovingAverage(8)
    yield api
    api.app.dependency_overrides.clear()


def test_the_forecast_route_refuses_a_user_who_hammers_it_and_not_the_others(limited, amir, siti):
    statuses = [limited.get("/api/forecast", headers=amir).status_code for _ in range(31)]
    assert statuses[:30] == [200] * 30
    assert statuses[30] == 429
    refused = limited.get("/api/forecast", headers=amir)
    assert refused.json()["detail"]["code"] == "too_many_requests"
    assert int(refused.headers["Retry-After"]) > 0
    assert limited.get("/api/forecast", headers=siti).status_code == 200


def test_the_confirm_route_is_limited_too(limited, amir):
    body = {
        "rows": [{"date": "2025-05-01", "amount_sen": 100, "type": "expense", "category": "Food"}]
    }
    statuses = [
        limited.post("/api/import/confirm", json=body, headers=amir).status_code for _ in range(11)
    ]
    assert all(s == 200 for s in statuses[:10])
    assert statuses[10] == 429


def test_create_app_gives_every_app_its_own_limiter(api):
    other = create_app(api.app.state.settings, db=api.app.state.db)
    assert other.state.request_limiter is not api.app.state.request_limiter
