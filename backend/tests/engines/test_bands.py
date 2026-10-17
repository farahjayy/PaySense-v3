"""The forecast band's widening by history length (WP16, change C2)."""

import json

import numpy as np
import pytest

from app.engines.forecasting import bands
from app.engines.forecasting.bands import BandRuleError, load_band_rule, parse_rule, text_digest
from app.engines.forecasting.service import MIN_SERIES_WEEKS, V1_ERROR_INFLATION, error_record

RULE = {
    "version": "2",
    "buckets": [
        {"min_weeks": 17, "spend": 2.5, "income": 3.0},
        {"min_weeks": 26, "spend": 2.0, "income": 2.4},
        {"min_weeks": 52, "spend": 1.6, "income": 1.8},
    ],
}


def test_the_factor_depends_on_history_length_and_kind():
    rule = parse_rule(RULE)
    assert rule.factor(17, "spend") == 2.5
    assert rule.factor(25, "income") == 3.0
    assert rule.factor(26, "spend") == 2.0
    assert rule.factor(51, "income") == 2.4
    assert rule.factor(400, "spend") == 1.6


def test_a_history_shorter_than_the_first_bucket_uses_the_first():
    assert parse_rule(RULE).factor(5, "spend") == 2.5


def test_an_unknown_kind_is_an_error():
    with pytest.raises(ValueError):
        parse_rule(RULE).factor(30, "bills")


@pytest.mark.parametrize(
    "broken",
    [
        {"version": "2", "buckets": []},
        {
            "version": "2",
            "buckets": [
                {"min_weeks": 26, "spend": 2, "income": 2},
                {"min_weeks": 17, "spend": 2, "income": 2},
            ],
        },  # fmt: skip
        {"version": "2", "buckets": [{"min_weeks": 17, "spend": 0.9, "income": 2}]},
        {"buckets": [{"min_weeks": 17, "spend": 2, "income": 2}]},
        {"version": "2", "buckets": [{"min_weeks": 17, "spend": "x", "income": 2}]},
    ],
)
def test_a_malformed_or_narrowing_table_is_refused(broken):
    with pytest.raises(BandRuleError):
        parse_rule(broken)


def test_the_committed_table_loads_widens_every_record_and_starts_at_the_gate():
    rule = load_band_rule()
    for kind in ("spend", "income"):
        assert min(getattr(b, kind) for b in rule.buckets) >= 1.0
    assert rule.buckets[0].min_weeks == MIN_SERIES_WEEKS


def test_the_digest_ignores_line_endings(tmp_path):
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    text = json.dumps(RULE, indent=2)
    lf.write_bytes(text.encode())
    crlf.write_bytes(text.replace("\n", "\r\n").encode())
    assert text_digest(lf) == text_digest(crlf)


def test_a_missing_table_is_a_clear_error(tmp_path):
    with pytest.raises(BandRuleError, match="cannot read"):
        bands.load_band_rule(tmp_path / "nope.json")


class Flat:
    name = "flat"

    def forecast(self, history, horizon, start):
        return np.full(horizon, float(np.mean(history)))


def test_a_record_too_short_to_score_falls_back_to_the_series_spread():
    values = np.arange(17, dtype=float)
    errors, fallback = error_record(values, None, Flat(), "spend")
    assert fallback and errors.shape == (1, 17)


def test_a_long_enough_record_is_the_users_own_error_paths():
    values = np.arange(40, dtype=float)
    errors, fallback = error_record(values, None, Flat(), "spend")
    assert not fallback and errors.shape[1] == 8


def test_v2s_single_factor_is_kept_only_for_the_comparison():
    assert V1_ERROR_INFLATION == 1.5
