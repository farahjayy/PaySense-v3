"""Run the Engine 1 comparison: `python -m ml.engine1_eval.run --config small|full` (plan P3, B11).

Streams one row per series x origin x model into `data/engine1/<config>/` (gitignored). Every model
is scored on exactly the same series and origins. A model that raises on a series is recorded in
`failures.csv` and the run continues, so a crash is never silently scored as a result.
"""

import argparse
import csv
import json
import platform
from collections.abc import Iterator, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import torch
import yaml

from ml.engine1_eval.data import Series, sample_profiles
from ml.engine1_eval.forecaster import Forecaster
from ml.engine1_eval.harness import EvalConfig, evaluate_pair, evaluate_series
from ml.engine1_eval.loaders import berka, moneydata, synthetic
from ml.engine1_eval.models.arima import AutoArima
from ml.engine1_eval.models.benchmarks import MovingAverage, Naive
from ml.engine1_eval.models.lstm import GlobalLstm, LstmConfig
from ml.engine1_eval.models.prophet_model import ProphetModel

CONFIG_DIR = Path(__file__).resolve().parent / "configs"
DEFAULT_OUT_ROOT = Path(__file__).resolve().parents[3] / "data" / "engine1"
KINDS = ("spend", "income")
BENCHMARKS = ("naive", "ma4", "ma13")
LITERATURE = ("arima", "prophet", "lstm")


@dataclass(frozen=True)
class RunConfig:
    name: str
    seed: int
    horizon: int
    report_horizons: list[int]
    stride: int
    min_train: int
    models: list[str]
    synthetic: dict[str, Any]
    moneydata: dict[str, Any]
    berka: dict[str, Any]
    lstm: dict[str, Any]


@dataclass(frozen=True)
class DataPaths:
    synthetic: Path = synthetic.DEFAULT_PATH
    moneydata: Path = moneydata.DEFAULT_PATH
    berka_account: Path = berka.DEFAULT_DIR / "account.csv"
    berka_trans: Path = berka.DEFAULT_DIR / "trans.csv"


def load_config(name_or_path: str) -> RunConfig:
    path = Path(name_or_path)
    if not path.suffix:
        path = CONFIG_DIR / f"{name_or_path}.yaml"
    config = RunConfig(**yaml.safe_load(path.read_text(encoding="utf-8")))
    unknown = set(config.models) - {*BENCHMARKS, *LITERATURE}
    if unknown:
        raise ValueError(f"unknown models {sorted(unknown)}; candidates are fixed by D-05")
    return config


def build_forecasters(
    names: Sequence[str], kind: str, lstm: dict[str, GlobalLstm]
) -> list[Forecaster]:
    factories = {
        "naive": Naive,
        "ma4": lambda: MovingAverage(4),
        "ma13": lambda: MovingAverage(13),
        "arima": AutoArima,
        "prophet": ProphetModel,
    }
    return [lstm[kind] if name == "lstm" else factories[name]() for name in names]


def result_columns(config: RunConfig) -> list[str]:
    last = config.horizon
    return [
        "history_limit", "series_id", "kind", "source", "model", "origin", "train_len", "scale",
        *(f"mase_{h}" for h in config.report_horizons),
        f"rmsse_{last}", f"coverage_{last}", f"width_{last}",
    ]  # fmt: skip


def margin_columns(config: RunConfig) -> list[str]:
    return [
        "history_limit", "series_id", "source", "model", "origin", "scale",
        *(f"margin_{h}" for h in config.report_horizons),
    ]  # fmt: skip


class _Output:
    def __init__(self, directory: Path, config: RunConfig) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self._files = []
        self.results = self._writer("results.csv", result_columns(config))
        self.margin = self._writer("margin.csv", margin_columns(config))
        self.failures = self._writer("failures.csv", ["source", "series_id", "model", "error"])
        self.failure_count = 0
        self.row_count = 0
        self.seconds: dict[tuple[str, str, str], list[float]] = {}

    def _writer(self, name: str, columns: list[str]) -> csv.DictWriter:
        handle = (self.directory / name).open("w", encoding="utf-8", newline="")
        self._files.append(handle)
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        return writer

    def close(self) -> None:
        for handle in self._files:
            handle.close()
        with (self.directory / "timing.csv").open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(["source", "history_limit", "model", "seconds", "origins"])
            for (source, limit, model), (seconds, origins) in sorted(self.seconds.items()):
                writer.writerow([source, limit, model, f"{seconds:.3f}", int(origins)])


def _pairs(series: Iterator[Series]) -> Iterator[dict[str, Series]]:
    waiting: dict[tuple[str, str], dict[str, Series]] = {}
    for s in series:
        key = (s.source, s.series_id)
        waiting.setdefault(key, {})[s.kind] = s
        if len(waiting[key]) == len(KINDS):
            yield waiting.pop(key)


def _train_lstms(config: RunConfig, series: list[Series], until: date) -> dict[str, GlobalLstm]:
    settings = {**config.lstm, "horizon": config.horizon, "seed": config.seed}
    lstm_config = LstmConfig(**settings)
    return {
        kind: GlobalLstm.train([s for s in series if s.kind == kind], lstm_config, until=until)
        for kind in KINDS
    }


def _synthetic_series(
    config: RunConfig, paths: DataPaths
) -> tuple[list[Series], list[dict[str, Series]]]:
    settings = config.synthetic
    train_ids, test_ids = sample_profiles(
        settings["profiles"], config.seed, settings["train_profiles"], settings["test_profiles"]
    )
    wanted = set(train_ids) | set(test_ids)
    train: list[Series] = []
    test: list[Series] = []
    for s in synthetic.load_synthetic(paths.synthetic, profile_ids=wanted):
        (test if int(s.series_id.split("-")[1]) in set(test_ids) else train).append(s)
    return train, list(_pairs(iter(test)))


def run(config: RunConfig, out_root: Path, paths: DataPaths | None = None) -> dict[str, Any]:
    paths = paths or DataPaths()
    out = _Output(out_root, config)
    base = EvalConfig(
        horizon=config.horizon,
        report_horizons=tuple(config.report_horizons),
        min_train=config.min_train,
        stride=config.stride,
    )
    lstm_models: dict[str, GlobalLstm] = {}
    try:
        train, test_pairs = _synthetic_series(config, paths)
        if train and test_pairs:
            cutoff = train[0].start + timedelta(weeks=config.synthetic["cutoff_week"])
            if "lstm" in config.models:
                lstm_models = _train_lstms(config, train, until=cutoff)
            for limit in config.synthetic["history_limits"]:
                eval_config = replace(base, history_limit=limit, first_origin_date=cutoff)
                for pair in test_pairs:
                    _score_pair(out, pair, config, lstm_models, eval_config, str(limit))
        _run_real(config, paths, out, base, lstm_models)
    finally:
        out.close()
    description = {
        "config": asdict(config),
        "versions": {
            "python": platform.python_version(),
            "numpy": np.__version__,
            "torch": torch.__version__,
        },
        "lstm_parameters": {k: m.parameter_count for k, m in lstm_models.items()},
    }
    (out_root / "run.json").write_text(
        json.dumps(description, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8"
    )
    return {"failures": out.failure_count, "rows": out.row_count}


def _score_pair(
    out: _Output,
    pair: dict[str, Series],
    config: RunConfig,
    lstm: dict[str, GlobalLstm],
    eval_config: EvalConfig,
    limit: str,
) -> None:
    """Score one student's / account's spend and income series with every model.

    Spend and income each get their own LSTM; every other model is the same for both kinds.
    """
    models = {kind: build_forecasters(config.models, kind, lstm) for kind in KINDS}
    for kind in KINDS:
        for model in models[kind]:
            _score_series(out, pair[kind], model, eval_config, limit)
    for spend_model, income_model in zip(models["spend"], models["income"], strict=True):
        try:
            rows = evaluate_pair(
                pair["spend"], pair["income"], spend_model, eval_config, income_model
            )
        except Exception as error:  # noqa: BLE001 - recorded, never swallowed
            _record_failure(out, pair["spend"], spend_model, error)
            continue
        for row in rows:
            out.margin.writerow({**row, "history_limit": limit})


def _score_series(
    out: _Output, series: Series, model: Forecaster, eval_config: EvalConfig, limit: str
) -> None:
    try:
        evaluation = evaluate_series(series, model, eval_config)
    except Exception as error:  # noqa: BLE001 - recorded, never swallowed
        _record_failure(out, series, model, error)
        return
    for row in evaluation.rows:
        out.results.writerow({**row, "history_limit": limit})
        out.row_count += 1
    bucket = out.seconds.setdefault((series.source, limit, model.name), [0.0, 0.0])
    bucket[0] += evaluation.seconds
    bucket[1] += len(evaluation.rows) + evaluation.skipped


def _record_failure(out: _Output, series: Series, model: Forecaster, error: Exception) -> None:
    out.failures.writerow(
        {
            "source": series.source,
            "series_id": series.series_id,
            "model": model.name,
            "error": f"{type(error).__name__}: {error}",
        }
    )
    out.failure_count += 1


def _run_real(
    config: RunConfig,
    paths: DataPaths,
    out: _Output,
    base: EvalConfig,
    lstm: dict[str, GlobalLstm],
) -> None:
    groups: list[tuple[list[dict[str, Series]], int]] = []
    if config.moneydata.get("enabled"):
        pairs = list(_pairs(moneydata.load_moneydata(paths.moneydata)))
        groups.append((pairs, config.moneydata["stride"]))
    if config.berka.get("accounts", 0) > 0:
        loaded = berka.load_berka(
            paths.berka_account, paths.berka_trans, min_weeks=config.berka["min_weeks"]
        )
        chosen = _sample(list(_pairs(loaded)), config.berka["accounts"], config.seed)
        groups.append((chosen, config.berka["stride"]))
    for pairs, stride in groups:
        eval_config = replace(base, stride=stride)
        for pair in pairs:
            _score_pair(out, pair, config, lstm, eval_config, "")


def _sample(pairs: list[dict[str, Series]], count: int, seed: int) -> list[dict[str, Series]]:
    order = np.random.default_rng(seed).permutation(len(pairs))[:count]
    return [pairs[i] for i in sorted(order)]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the Engine 1 forecaster comparison.")
    parser.add_argument("--config", default="small")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    config = load_config(args.config)
    summary = run(config, args.out or DEFAULT_OUT_ROOT / config.name)
    print(f"{config.name}: {summary['rows']} rows, {summary['failures']} failures")  # noqa: T201


if __name__ == "__main__":
    main()
