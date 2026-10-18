"""The recursion check: cumulative-total error of the served LSTM beyond 13 weeks (no LSTM here)."""

from datetime import date

import numpy as np
import pytest

from app.engines.forecasting.bands import parse_rule
from app.engines.forecasting.models import MovingAverage, Naive
from ml.engine1_eval.recursion_check import (
    HORIZONS,
    MODELS,
    ORIGINS,
    BandScore,
    Errors,
    band_rows,
    band_scores,
    render,
    scaled_errors,
    summarise,
    summary_rows,
)

START = date(2024, 7, 1)


def test_the_error_is_the_cumulative_total_gap_as_a_share_of_the_recent_level():
    values = np.concatenate([np.full(26, 10.0), np.full(52, 20.0)])
    errors = scaled_errors(values, START, 26, MovingAverage(13))
    assert errors == pytest.approx([-1.0] * len(HORIZONS))  # forecast 10 a week, actual 20
    over = scaled_errors(np.concatenate([np.full(26, 10.0), np.full(52, 5.0)]), START, 26, Naive())
    assert over == pytest.approx([0.5] * len(HORIZONS))


def test_a_series_with_no_recent_level_is_left_out():
    values = np.concatenate([np.full(26, 0.0), np.full(52, 20.0)])
    assert scaled_errors(values, START, 26, MovingAverage(13)) is None


class _Spy:
    name = "spy"

    def __init__(self) -> None:
        self.seen: list[int] = []

    def forecast(self, history, horizon, start):
        assert not np.any(np.asarray(history) >= 1e9)
        self.seen.append(len(history))
        return np.full(horizon, 1.0)


@pytest.mark.parametrize("origin", ORIGINS)
def test_the_forecaster_sees_only_the_weeks_before_the_origin(origin):
    values = np.full(78, 10.0)
    values[origin:] = 1e9
    spy = _Spy()
    scaled_errors(values, START, origin, spy)
    assert spy.seen == [origin]


def test_summarise():
    stats = summarise(np.array([-1.0, 1.0, 3.0]))
    assert stats == {"median": 1.0, "mae": pytest.approx(5 / 3), "median_abs": 1.0}


def _records() -> list[Errors]:
    out = []
    for kind in ("spend", "income"):
        for origin in ORIGINS:
            for profile, shift in ((4001, 0.1), (4002, -0.2)):
                for model in MODELS:
                    gap = {"lstm": -0.3, "ma13": 0.05, "naive": -0.5}[model] + shift
                    out.append(Errors(profile, kind, origin, model, tuple([gap] * len(HORIZONS))))
    return out


def test_the_page_and_rows_cover_every_kind_origin_model_and_horizon():
    records = _records()
    page = render(records, {("income", 17): 1}, [4001, 4002])
    assert "do not edit by hand" in page
    for label in ("served LSTM (recursive)", "MA13 (benchmark)", "naive (benchmark)"):
        assert page.count(f"| {label} |") == 2 * len(ORIGINS)
    for h in HORIZONS:
        assert f"{h} weeks" in page
    assert "nan" not in page
    rows = summary_rows(records)
    assert len(rows) == 2 * len(ORIGINS) * len(MODELS) * len(HORIZONS)
    lstm = next(r for r in rows if r["model"] == "lstm" and r["kind"] == "spend")
    assert lstm["series"] == 2 and lstm["median"] == pytest.approx(-0.35)
    assert lstm["share_lstm_beats_ma13"] == 0.0  # |-0.2| > |0.15| and |-0.5| > |-0.15|


# --- engine v3: the simulated band of the cumulative total beyond 13 weeks, R2 against R3 ------

FLAT_RULE = parse_rule(
    {"version": "2", "buckets": [{"min_weeks": 17, "spend": 1.0, "income": 1.0}]}
)


def test_an_exact_forecast_with_no_error_is_inside_its_band_with_no_bias():
    values = np.full(78, 10.0)
    rng = np.random.default_rng(0)
    inside, bias = band_scores(values, START, 26, MovingAverage(13), "spend", FLAT_RULE, rng)
    assert inside == [True] * len(HORIZONS)
    assert bias == pytest.approx([0.0] * len(HORIZONS))
    assert band_scores(np.zeros(78), START, 26, MovingAverage(13), "spend", FLAT_RULE, rng) is None


def test_a_forecast_too_low_with_no_spread_misses_and_shows_its_bias():
    values = np.concatenate([np.full(26, 10.0), np.full(52, 20.0)])
    rng = np.random.default_rng(0)
    inside, bias = band_scores(values, START, 26, MovingAverage(13), "spend", FLAT_RULE, rng)
    assert not any(inside)
    assert bias == pytest.approx([-1.0] * len(HORIZONS))


def test_band_rows_and_the_page_section():
    scores = [
        BandScore(p, kind, origin, rule, tuple([p == 4001] * len(HORIZONS)), (0.1,) * len(HORIZONS))
        for p in (4001, 4002)
        for kind in ("spend", "income")
        for origin in ORIGINS
        for rule in ("R2", "R3")
    ]
    rows = band_rows(scores)
    assert len(rows) == 2 * len(ORIGINS) * 2 * len(HORIZONS)
    assert all(r["coverage"] == 0.5 and r["median_bias"] == pytest.approx(0.1) for r in rows)
    page = render(_records(), {}, [4001, 4002], scores)
    assert "## The simulated band beyond 13 weeks: R2 against R3" in page
    assert page.count("| R3 |") == 2 * len(ORIGINS)
