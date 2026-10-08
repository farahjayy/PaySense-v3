import csv
import hashlib
import json
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from ml.engine1_eval.report import build_report, select_model
from ml.engine1_eval.run import DataPaths, RunConfig, run


def scores(rows):
    return pd.DataFrame(rows, columns=["source", "series_id", "kind", "model", "mase"])


def table(models, count=60, seed=0):
    """`models` maps a model name to (mean, spread) of its per-series MASE on `count` series."""
    rng = np.random.default_rng(seed)
    rows = []
    for name, (mean, spread) in models.items():
        for i in range(count):
            rows.append(("synthetic", f"s{i}", "spend", name, mean + rng.normal(0, spread)))
    return scores(rows)


def test_a_clearly_better_literature_model_is_served():
    choice = select_model(
        table({"naive": (1.0, 0.1), "ma4": (0.95, 0.1), "arima": (0.8, 0.1), "prophet": (0.9, 0.1)})
    )

    assert choice.best_literature == "arima" and choice.best_benchmark == "ma4"
    assert choice.served == "arima" and choice.branch == "literature"


def test_a_benchmark_that_is_significantly_and_materially_better_is_served_and_said_so():
    choice = select_model(
        table({"naive": (0.9, 0.1), "ma4": (0.7, 0.1), "arima": (0.95, 0.1), "prophet": (1.0, 0.1)})
    )

    assert choice.served == "ma4" and choice.branch == "benchmark"
    assert choice.p_value < 0.05 and choice.median_difference >= 0.02


def test_a_significant_but_trivial_benchmark_lead_does_not_override_the_literature_model():
    models = {"naive": (1.0, 0.01), "ma4": (0.99, 0.01), "arima": (0.995, 0.01)}
    # a 0.005 lead is statistically detectable with tight spreads but below the 0.02 floor
    choice = select_model(table(models, count=200))

    assert choice.served == "arima" and choice.branch == "literature"


def test_a_benchmark_lead_that_is_not_significant_does_not_override_the_literature_model():
    # three paired series: the benchmark leads by 0.5 each time, but three pairs cannot reach
    # p < 0.05 in a Wilcoxon test (the smallest possible p is 0.25)
    rows = []
    for i in range(3):
        rows.append(("synthetic", f"s{i}", "spend", "ma4", 1.0 + 0.01 * i))
        rows.append(("synthetic", f"s{i}", "spend", "arima", 1.5 + 0.01 * i))

    choice = select_model(scores(rows))

    assert choice.median_difference == pytest.approx(0.5)
    assert choice.served == "arima" and choice.branch == "literature"


def test_the_decision_weights_every_source_equally_not_every_series():
    rows = [
        ("synthetic", f"s{i}", "spend", m, v)
        for i in range(100)
        for m, v in (("ma4", 1.0), ("arima", 0.5))
    ]
    rows += [("berka", "b1", "spend", m, v) for m, v in (("ma4", 1.0), ("arima", 5.0))]

    choice = select_model(scores(rows))

    # arima: mean(0.5, 5.0) = 2.75 against ma4's 1.0 - one bad source counts as much as a big one
    assert choice.metric["arima"] == pytest.approx(2.75) and choice.metric["ma4"] == pytest.approx(
        1.0
    )


def test_a_comparison_without_a_literature_candidate_or_a_benchmark_is_rejected():
    with pytest.raises(ValueError, match="benchmark"):
        select_model(table({"arima": (1.0, 0.1), "prophet": (0.9, 0.1)}))
    with pytest.raises(ValueError, match="literature"):
        select_model(table({"naive": (1.0, 0.1), "ma4": (0.9, 0.1)}))


COHORT_START = date(2024, 7, 1)


@pytest.fixture(scope="module")
def stored(tmp_path_factory):
    root = tmp_path_factory.mktemp("engine1")
    cohort = root / "weekly_series.csv"
    rng = np.random.default_rng(0)
    with cohort.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["profile_index", "week_start", "discretionary_sen", "income_sen"])
        for index in range(40):
            for week in range(80):
                day = COHORT_START + timedelta(weeks=week)
                writer.writerow(
                    [index, day.isoformat(), int(rng.uniform(50, 150)), int(rng.uniform(0, 400))]
                )
    config = RunConfig(
        name="unit",
        seed=1,
        horizon=4,
        report_horizons=[1, 4],
        stride=4,
        min_train=10,
        models=["naive", "ma4", "ma13", "lstm"],
        synthetic={
            "profiles": 40,
            "train_profiles": 25,
            "test_profiles": 12,
            "cutoff_week": 40,
            "history_limits": [12, 30],
        },
        moneydata={"enabled": False},
        berka={"accounts": 0},
        lstm={"hidden": 4, "epochs": 1, "window": 8},
    )
    run(config, root / "run", DataPaths(synthetic=cohort))
    return root / "run"


def test_the_report_writes_tables_figures_a_selection_and_a_readme(stored, tmp_path):
    build_report(stored, tmp_path)

    for name in (
        "README.md",
        "selection.json",
        "tables/pooled_mase.csv",
        "tables/coverage.csv",
        "tables/margin.csv",
        "tables/by_history.csv",
        "tables/timing.csv",
        "tables/friedman.csv",
    ):
        assert (tmp_path / name).is_file(), name
    assert list((tmp_path / "figures").glob("*.png"))


def test_every_table_contains_the_benchmarks(stored, tmp_path):
    build_report(stored, tmp_path)

    for name in ("pooled_mase", "coverage", "margin", "by_history", "timing"):
        models = set(pd.read_csv(tmp_path / "tables" / f"{name}.csv")["model"])
        assert {"naive", "ma4"} <= models, name


def test_the_readme_states_the_rule_that_fired_and_the_caveats(stored, tmp_path):
    build_report(stored, tmp_path)

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    selection = json.loads((tmp_path / "selection.json").read_text(encoding="utf-8"))
    assert f"**Served model: `{selection['served']}`**" in readme
    assert selection["branch"] in {"literature", "benchmark"}
    assert "circular" in readme.lower()
    assert "not available" in readme.lower() or "unavailable" in readme.lower()
    assert "python -m ml.engine1_eval.report" in readme


def test_failures_are_surfaced_in_the_readme(stored, tmp_path):
    import shutil

    broken = tmp_path / "broken_run"
    shutil.copytree(stored, broken)
    (broken / "failures.csv").write_text(
        "source,series_id,model,error\nsynthetic,syn-1,arima,ValueError: boom\n", encoding="utf-8"
    )

    build_report(broken, tmp_path / "out")

    assert "Model failures recorded: 1" in (tmp_path / "out" / "README.md").read_text(
        encoding="utf-8"
    )


def test_a_series_a_model_failed_on_is_dropped_for_every_model_before_averaging():
    rows = []
    for i in range(10):
        rows += [("synthetic", f"s{i}", "spend", m, v) for m, v in (("ma4", 1.0), ("arima", 0.5))]
    rows += [("synthetic", "hard", "spend", "ma4", 9.0)]  # arima failed on the hard series

    choice = select_model(scores(rows))

    assert choice.dropped_series == 1 and choice.n_series == 10
    assert choice.metric["ma4"] == pytest.approx(1.0)  # the hard series did not inflate it


def test_a_comparison_with_no_series_scored_by_every_model_is_rejected():
    rows = [("synthetic", "a", "spend", "ma4", 1.0), ("synthetic", "b", "spend", "arima", 1.0)]

    with pytest.raises(ValueError, match="every model"):
        select_model(scores(rows))


def test_the_readme_reports_the_margin_rank_of_the_served_model_and_the_bias(stored, tmp_path):
    build_report(stored, tmp_path)

    readme = (tmp_path / "README.md").read_text(encoding="utf-8")
    assert "cumulative-margin error" in readme and "ranks" in readme
    assert (tmp_path / "tables" / "bias.csv").is_file()
    assert (tmp_path / "tables" / "selection_by_history.csv").is_file()


def test_regenerating_gives_identical_files(stored, tmp_path):
    build_report(stored, tmp_path / "a")
    build_report(stored, tmp_path / "b")

    names = ["README.md", "selection.json", "tables/pooled_mase.csv", "tables/friedman.csv"]
    for name in names:
        a = hashlib.sha256((tmp_path / "a" / name).read_bytes()).hexdigest()
        b = hashlib.sha256((tmp_path / "b" / name).read_bytes()).hexdigest()
        assert a == b, name


def test_one_series_with_a_huge_error_cannot_decide_between_two_models():
    rows = []
    for i in range(20):
        rows.append(("synthetic", f"s{i}", "spend", "arima", 0.8))
        rows.append(("synthetic", f"s{i}", "spend", "ma4", 1.0))
    rows[-2] = ("synthetic", "s19", "spend", "arima", 30.0)  # one series where arima blew up

    choice = select_model(scores(rows))

    assert choice.arithmetic_metric["arima"] > choice.arithmetic_metric["ma4"]  # the mean is fooled
    assert choice.metric["arima"] < choice.metric["ma4"]  # the geometric mean is not
    assert choice.served == "arima"
