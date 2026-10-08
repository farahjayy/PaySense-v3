"""The four Engine 2 candidates (ADR D-05) trained on a soft target (plan P5, task D6).

* Soft labels use duplicate-and-weight: each profile appears once as class 1 with weight p and
  once as class 0 with weight 1 - p. It works identically for every model.
* Random Forest, XGBoost and LightGBM carry monotone constraints on the features whose direction
  of effect on risk is known (`MONOTONE_DIRECTIONS`); the logistic regression is the benchmark.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import lightgbm as lgb
import numpy as np
import optuna
import xgboost as xgb
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from app.engines.risk.features import MONOTONE_DIRECTIONS

CANDIDATES = ("logistic", "lightgbm", "xgboost", "random_forest")  # simplest first
SEED = 0


@dataclass
class Fitted:
    name: str
    model: Any
    features: tuple[str, ...]

    def predict(self, x: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(x)[:, 1]


def expand_soft(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Duplicate-and-weight: each profile once as class 1 (weight p), once as class 0 (1 - p)."""
    n = len(y)
    return (
        np.vstack([x, x]),
        np.concatenate([np.ones(n), np.zeros(n)]),
        np.concatenate([y, 1 - y]),
    )


def _constraints(features: tuple[str, ...]) -> list[int]:
    return [MONOTONE_DIRECTIONS[name] for name in features]


def build(name: str, params: dict[str, Any], features: tuple[str, ...], seed: int = SEED) -> Any:
    if name == "logistic":
        return make_pipeline(
            StandardScaler(), LogisticRegression(C=params.get("C", 1.0), max_iter=2000)
        )
    constraints = _constraints(features)
    if name == "random_forest":
        return RandomForestClassifier(
            n_estimators=params.get("n_estimators", 200),
            max_depth=params.get("max_depth", 8),
            min_samples_leaf=params.get("min_samples_leaf", 20),
            monotonic_cst=constraints,
            n_jobs=-1,
            random_state=seed,
        )
    if name == "xgboost":
        return xgb.XGBClassifier(
            n_estimators=params.get("n_estimators", 200),
            max_depth=params.get("max_depth", 3),
            learning_rate=params.get("learning_rate", 0.1),
            subsample=params.get("subsample", 0.9),
            colsample_bytree=params.get("colsample_bytree", 0.9),
            min_child_weight=params.get("min_child_weight", 5),
            reg_lambda=params.get("reg_lambda", 1.0),
            monotone_constraints=tuple(constraints),
            n_jobs=1,
            random_state=seed,
            verbosity=0,
        )
    if name == "lightgbm":
        return lgb.LGBMClassifier(
            n_estimators=params.get("n_estimators", 200),
            num_leaves=params.get("num_leaves", 8),
            learning_rate=params.get("learning_rate", 0.1),
            subsample=params.get("subsample", 0.9),
            subsample_freq=1,
            colsample_bytree=params.get("colsample_bytree", 0.9),
            min_child_samples=params.get("min_child_samples", 30),
            monotone_constraints=constraints,
            n_jobs=1,
            random_state=seed,
            verbose=-1,
        )
    raise ValueError(f"unknown model {name!r}; candidates are fixed by D-05: {CANDIDATES}")


def fit_soft(
    name: str,
    params: dict[str, Any],
    x: np.ndarray,
    y: np.ndarray,
    features: tuple[str, ...],
    seed: int = SEED,
) -> Fitted:
    x2, y2, w2 = expand_soft(x, y)
    model = build(name, params, features, seed)
    if name == "logistic":
        model.fit(x2, y2, logisticregression__sample_weight=w2)
    else:
        model.fit(x2, y2, sample_weight=w2)
    return Fitted(name, model, features)


def suggest(name: str, trial: optuna.Trial) -> dict[str, Any]:
    """The search space of each candidate (Optuna)."""
    if name == "logistic":
        return {"C": trial.suggest_float("C", 1e-3, 1e2, log=True)}
    if name == "random_forest":
        return {
            "n_estimators": trial.suggest_int("n_estimators", 100, 300, step=50),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "min_samples_leaf": trial.suggest_int("min_samples_leaf", 5, 60),
        }
    shared = {
        "n_estimators": trial.suggest_int("n_estimators", 100, 400, step=50),
        "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.3, log=True),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
    }
    if name == "xgboost":
        return {
            **shared,
            "max_depth": trial.suggest_int("max_depth", 2, 6),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 20),
            "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 10.0, log=True),
        }
    return {
        **shared,
        "num_leaves": trial.suggest_int("num_leaves", 4, 31),
        "min_child_samples": trial.suggest_int("min_child_samples", 10, 100),
    }


def tune(
    name: str,
    x: np.ndarray,
    y: np.ndarray,
    features: tuple[str, ...],
    trials: int,
    seed: int,
    scorer: Callable[[np.ndarray, np.ndarray], float],
) -> dict[str, Any]:
    """Pick hyperparameters on an inner 80/20 split of the TRAINING data only (Optuna, seeded)."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(y))
    cut = int(0.8 * len(y))
    fit_idx, valid_idx = order[:cut], order[cut:]
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        fitted = fit_soft(name, suggest(name, trial), x[fit_idx], y[fit_idx], features, seed)
        return scorer(fitted.predict(x[valid_idx]), y[valid_idx])

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=trials)
    return dict(study.best_params)
