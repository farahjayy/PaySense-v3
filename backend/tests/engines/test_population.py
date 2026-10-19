"""F2 (engine v3, D-61): a population error record for short histories, guarded by its digest."""

import hashlib
import json
from datetime import date

import numpy as np
import pytest

from app.engines.forecasting.bands import BandRuleError, load_band_rule, parse_rule
from app.engines.forecasting.population import (
    PopulationError,
    load_population,
    recent_level,
    write_population,
)
from app.engines.forecasting.series import WeeklySeries
from app.engines.forecasting.service import served_error_records
from app.engines.risk.artefact import live_constants

PATHS = {
    "spend": [[0.5, -0.5, 0.25] + [0.0] * 10, [-0.2] * 13],
    "income": [[0.1] * 13],
}


class Flat:
    name = "flat"

    def forecast(self, history, horizon, start):
        return np.full(horizon, float(np.mean(history)))


def _write(folder, paths=PATHS, below=26, clip="month"):
    record = folder / "population_errors.json"
    write_population(record, paths, {"students": 2})
    digest = hashlib.sha256(record.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    rule = {
        "version": "3",
        "clip": clip,
        "population_record": {"file": record.name, "sha256": digest, "below_weeks": below},
        "buckets": [
            {"min_weeks": 17, "spend": 2.0, "income": 1.0},
            {"min_weeks": 26, "spend": 1.5, "income": 1.0},
        ],
    }
    path = folder / "band_inflation.json"
    path.write_text(json.dumps(rule), encoding="utf-8")
    return path, record, digest


def _series(weeks, spend=1000.0, income=0.0):
    return WeeklySeries(
        date(2024, 1, 1),
        np.full(weeks, spend).astype(np.int64),
        np.full(weeks, income).astype(np.int64),
    )


def test_the_record_round_trips_and_carries_its_provenance(tmp_path):
    _, record, digest = _write(tmp_path)
    loaded = load_population(record, digest)
    assert loaded.paths["spend"].shape == (2, 13)
    assert loaded.paths["income"].shape == (1, 13)
    assert json.loads(record.read_text())["fitted_on"] == {"students": 2}


def test_a_changed_record_is_refused(tmp_path):
    _, record, digest = _write(tmp_path)
    record.write_text(record.read_text().replace("0.5", "0.6"), encoding="utf-8")
    load_population.cache_clear()
    with pytest.raises(PopulationError, match="digest"):
        load_population(record, digest)


def test_a_malformed_record_is_refused(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"kinds": {"spend": [[1, 2], [3]]}}), encoding="utf-8")
    digest = hashlib.sha256(bad.read_bytes()).hexdigest()
    with pytest.raises(PopulationError):
        load_population(bad, digest)


def test_the_level_is_the_mean_of_the_last_26_weeks_or_all_of_a_shorter_history():
    assert recent_level(np.arange(10, dtype=float)) == pytest.approx(4.5)
    assert recent_level(np.r_[np.zeros(10), np.ones(26)]) == pytest.approx(1.0)


def test_the_rule_names_its_clip_and_its_population_record(tmp_path):
    path, _, digest = _write(tmp_path)
    rule = load_band_rule(path)
    assert rule.clip == "month"
    assert rule.population is not None and rule.population.sha256 == digest
    assert rule.population.below_weeks == 26
    assert (
        parse_rule({"version": "2", "buckets": [{"min_weeks": 17, "spend": 2, "income": 2}]}).clip
        == "week"
    )


@pytest.mark.parametrize(
    "change",
    [
        {"clip": "day"},
        {"population_record": {"file": "../x.json", "sha256": "a" * 64, "below_weeks": 26}},
        {"population_record": {"file": "x.json", "below_weeks": 26}},
        {"population_record": {"file": "x.json", "sha256": "a" * 64, "below_weeks": 5}},
    ],
)
def test_a_bad_clip_or_population_reference_is_refused(change):
    rule = {"version": "3", "buckets": [{"min_weeks": 17, "spend": 2, "income": 2}], **change}
    with pytest.raises(BandRuleError):
        parse_rule(rule)


def test_a_short_history_uses_the_population_paths_scaled_by_its_level(tmp_path):
    path, _, _ = _write(tmp_path)
    rule = load_band_rule(path)
    spend, income, fallback = served_error_records(_series(20), Flat(), rule)
    assert not fallback
    level = 1000.0
    expected = np.array(PATHS["spend"]) * level
    widened = expected.mean() + 2.0 * (expected - expected.mean())
    np.testing.assert_allclose(spend, widened)
    assert income.shape == (1, 13) and np.all(income == 0)  # no income: a level of zero


def test_from_26_weeks_the_users_own_record_is_used(tmp_path):
    path, _, _ = _write(tmp_path)
    rule = load_band_rule(path)
    spend, _, _ = served_error_records(_series(30), Flat(), rule)
    assert spend.shape[1] == 8  # the user's own eight-week paths, not the 13-week population ones


def test_a_rule_without_a_population_record_keeps_the_v2_behaviour():
    rule = parse_rule({"version": "2", "buckets": [{"min_weeks": 17, "spend": 2, "income": 1}]})
    spend, _, fallback = served_error_records(_series(20), Flat(), rule)
    assert spend.shape[1] == 8 or fallback


def test_a_rule_whose_record_is_missing_or_changed_refuses_to_serve(tmp_path):
    path, record, _ = _write(tmp_path)
    record.write_text(record.read_text().replace("0.5", "0.7"), encoding="utf-8")
    load_population.cache_clear()
    with pytest.raises(PopulationError):
        served_error_records(_series(20), Flat(), load_band_rule(path))


def test_engine2_records_the_population_digest():
    constants = live_constants()
    assert "POPULATION_RECORD_SHA256" in constants
    rule = load_band_rule()
    expected = rule.population.sha256 if rule.population else None
    assert constants["POPULATION_RECORD_SHA256"] == expected
