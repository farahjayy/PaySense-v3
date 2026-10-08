import csv
import json
from datetime import date, timedelta

import numpy as np
import pytest

from ml.engine1_eval.data import sample_profiles
from ml.engine1_eval.run import DataPaths, RunConfig, load_config, run

WEEKS = 80
COHORT_START = date(2024, 7, 1)


def write_cohort(path, profiles):
    rng = np.random.default_rng(0)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["profile_index", "week_start", "discretionary_sen", "income_sen"])
        for index in range(profiles):
            for week in range(WEEKS):
                day = COHORT_START + timedelta(weeks=week)
                writer.writerow(
                    [index, day.isoformat(), int(rng.uniform(50, 150)), int(rng.uniform(0, 400))]
                )


def config(**overrides):
    base = {
        "name": "unit",
        "seed": 1,
        "horizon": 4,
        "report_horizons": [1, 4],
        "stride": 4,
        "min_train": 10,
        "models": ["naive", "ma4"],
        "synthetic": {
            "profiles": 30,
            "train_profiles": 10,
            "test_profiles": 5,
            "cutoff_week": 40,
            "history_limits": [12, 30],
        },
        "moneydata": {"enabled": False},
        "berka": {"accounts": 0},
        "lstm": {"hidden": 4, "epochs": 1, "window": 8, "horizon": 4},
    }
    base.update(overrides)
    return RunConfig(**base)


@pytest.fixture(scope="module")
def cohort(tmp_path_factory):
    path = tmp_path_factory.mktemp("cohort") / "weekly_series.csv"
    write_cohort(path, 30)
    return path


def rows(path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_profile_sampling_is_disjoint_seeded_and_the_right_size():
    train, test = sample_profiles(total=50, seed=3, train=10, test=4)

    assert len(train) == 10 and len(test) == 4 and set(train).isdisjoint(test)
    assert sample_profiles(50, 3, 10, 4) == (train, test)
    assert sample_profiles(50, 4, 10, 4) != (train, test)


def test_a_run_writes_results_margin_timing_failures_and_the_run_description(cohort, tmp_path):
    summary = run(config(), tmp_path, DataPaths(synthetic=cohort))

    for name in ("results.csv", "margin.csv", "timing.csv", "failures.csv", "run.json"):
        assert (tmp_path / name).is_file(), name
    assert summary["failures"] == 0
    description = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert description["config"]["name"] == "unit" and "numpy" in description["versions"]


def test_every_model_is_scored_on_the_same_series_and_origins(cohort, tmp_path):
    run(config(), tmp_path, DataPaths(synthetic=cohort))

    data = rows(tmp_path / "results.csv")
    by_model = {}
    for r in data:
        by_model.setdefault(r["model"], set()).add(
            (r["series_id"], r["kind"], r["origin"], r["history_limit"])
        )

    assert set(by_model) == {"naive", "ma4"}
    assert by_model["naive"] == by_model["ma4"] and by_model["naive"]


def test_no_origin_falls_before_the_cutoff_week_and_only_test_profiles_are_scored(cohort, tmp_path):
    cfg = config()
    run(cfg, tmp_path, DataPaths(synthetic=cohort))

    data = rows(tmp_path / "results.csv")
    _, test = sample_profiles(30, cfg.seed, 10, 5)
    assert min(int(r["origin"]) for r in data) >= 40
    assert {r["series_id"] for r in data} <= {f"syn-{i}" for i in test}


def test_each_history_limit_is_run_and_labelled(cohort, tmp_path):
    run(config(), tmp_path, DataPaths(synthetic=cohort))

    limits = {r["history_limit"] for r in rows(tmp_path / "results.csv")}
    assert limits == {"12", "30"}
    assert {int(r["train_len"]) for r in rows(tmp_path / "results.csv")} <= {12, 30}


def test_a_failing_model_is_recorded_and_the_run_continues(cohort, tmp_path, monkeypatch):
    from ml.engine1_eval import run as run_module

    class Broken:
        name = "broken"

        def forecast(self, history, horizon, start):
            raise RuntimeError("boom")

    original = run_module.build_forecasters
    monkeypatch.setattr(
        run_module,
        "build_forecasters",
        lambda names, kind, lstm: [*original(names, kind, lstm), Broken()],
    )

    summary = run(config(), tmp_path, DataPaths(synthetic=cohort))

    assert summary["failures"] > 0
    failures = rows(tmp_path / "failures.csv")
    assert failures and all(f["model"] == "broken" and "boom" in f["error"] for f in failures)
    assert {r["model"] for r in rows(tmp_path / "results.csv")} == {"naive", "ma4"}


def test_two_runs_give_identical_result_files(cohort, tmp_path):
    run(config(), tmp_path / "a", DataPaths(synthetic=cohort))
    run(config(), tmp_path / "b", DataPaths(synthetic=cohort))

    for name in ("results.csv", "margin.csv"):
        assert (tmp_path / "a" / name).read_bytes() == (tmp_path / "b" / name).read_bytes()


def test_the_shipped_configurations_load_and_name_only_the_fixed_candidates():
    for name in ("small", "full"):
        cfg = load_config(name)
        assert cfg.name == name
        assert set(cfg.models) <= {"naive", "ma4", "ma13", "arima", "prophet", "lstm"}
        assert {"naive", "ma4"} <= set(cfg.models)  # benchmarks are in every comparison


def test_the_lstm_is_trained_per_kind_and_used_in_a_run(cohort, tmp_path):
    cfg = config(models=["naive", "lstm"])

    run(cfg, tmp_path, DataPaths(synthetic=cohort))

    data = rows(tmp_path / "results.csv")
    assert {r["model"] for r in data} == {"naive", "lstm"}
    assert {r["kind"] for r in data if r["model"] == "lstm"} == {"spend", "income"}


def test_the_lstm_without_synthetic_training_data_is_a_clear_error(cohort, tmp_path):
    bad = config(models=["naive", "lstm"], synthetic={**config().synthetic, "test_profiles": 0})

    with pytest.raises(ValueError, match="LSTM needs"):
        run(bad, tmp_path, DataPaths(synthetic=cohort))


def test_a_programming_error_stops_the_run_instead_of_being_recorded_as_a_result(
    cohort, tmp_path, monkeypatch
):
    from ml.engine1_eval import run as run_module

    class Buggy:
        name = "buggy"

        def forecast(self, history, horizon, start):
            raise TypeError("a real bug")

    original = run_module.build_forecasters
    monkeypatch.setattr(
        run_module,
        "build_forecasters",
        lambda names, kind, lstm: [*original(names, kind, lstm), Buggy()],
    )

    with pytest.raises(TypeError, match="real bug"):
        run(config(), tmp_path, DataPaths(synthetic=cohort))


def test_each_series_is_fitted_once_per_model_even_though_margin_error_is_reported(
    cohort, tmp_path, monkeypatch
):
    from ml.engine1_eval import run as run_module

    calls = []

    class Counting:
        name = "counting"

        def forecast(self, history, horizon, start):
            calls.append(len(history))
            return np.full(horizon, 1.0)

    monkeypatch.setattr(run_module, "build_forecasters", lambda names, kind, lstm: [Counting()])
    cfg = config(synthetic={**config().synthetic, "history_limits": [12], "test_profiles": 3})

    run(cfg, tmp_path, DataPaths(synthetic=cohort))

    from ml.engine1_eval.harness import rolling_origins

    origins = len(rolling_origins(80, 40, cfg.horizon, cfg.stride))
    assert len(calls) == 3 * 2 * origins  # profiles x kinds x origins: no second pass for margin
    assert len(rows(tmp_path / "margin.csv")) > 0
