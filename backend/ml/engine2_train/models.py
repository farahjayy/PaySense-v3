"""The four Engine 2 candidates (ADR D-05) trained on a soft target (plan P5, task D6).

* Soft labels use duplicate-and-weight: each profile appears once as class 1 with weight p and
  once as class 0 with weight 1 - p. It works identically for every model.
* Random Forest, XGBoost and LightGBM carry monotone constraints on the features whose direction
  of effect on risk is known (`MONOTONE_DIRECTIONS`); the logistic regression is the benchmark.
* Two-part target (engine v3, D-62): when the last column is `BASE_COLUMN` (the simulated chance
  b without the purchase), the model learns q = (p - b) / (1 - b), the chance the purchase makes
  short a path that was not short without it, with weight (1 - b) on top of duplicate-and-weight;
  its prediction is composed back, b + (1 - b) * q-hat, so every score is on the label's scale.
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
from ml.engine2_train.data import BASE_COLUMN

CANDIDATES = ("logistic", "lightgbm", "xgboost", "random_forest")  # simplest first
SEED = 0


@dataclass
class Fitted:
    name: str
    model: Any
    features: tuple[str, ...]  # the columns it is given; the last is BASE_COLUMN when two_part
    two_part: bool = False

    @property
    def model_features(self) -> tuple[str, ...]:
        """The columns the underlying model sees (never the base)."""
        return self.features[:-1] if self.two_part else self.features

    def predict_q(self, x_features: np.ndarray) -> np.ndarray:
        """The underlying model's output on feature columns only (q for a two-part model)."""
        return self.model.predict_proba(x_features)[:, 1]

    def predict(self, x: np.ndarray) -> np.ndarray:
        if not self.two_part:
            return self.predict_q(x)
        base = x[:, -1]
        return base + (1 - base) * self.predict_q(x[:, :-1])


def expand_soft(x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Duplicate-and-weight: each profile once as class 1 (weight p), once as class 0 (1 - p)."""
    n = len(y)
    return (
        np.vstack([x, x]),
        np.concatenate([np.ones(n), np.zeros(n)]),
        np.concatenate([y, 1 - y]),
    )


def two_part_target(y: np.ndarray, base: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(q, weight): q = (y - b) / (1 - b) in [0, 1], weight 1 - b (0 where b = 1, q then 0)."""
    y, base = np.asarray(y, dtype=float), np.asarray(base, dtype=float)
    weight = np.clip(1 - base, 0, 1)
    safe = np.where(weight > 0, weight, 1.0)
    q = np.where(weight > 0, np.clip((y - base) / safe, 0, 1), 0.0)
    return q, weight


def _constraints(features: tuple[str, ...]) -> list[int]:
    return [MONOTONE_DIRECTIONS[name] for name in features]


def build(
    name: str,
    params: dict[str, Any],
    features: tuple[str, ...],
    seed: int = SEED,
    constrained: bool = True,
) -> Any:
    if name == "logistic":
        return make_pipeline(
            StandardScaler(), LogisticRegression(C=params.get("C", 1.0), max_iter=2000)
        )
    constraints = _constraints(features) if constrained else None
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
            monotone_constraints=tuple(constraints) if constraints else None,
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
    constrained: bool = True,
) -> Fitted:
    two_part = bool(features) and features[-1] == BASE_COLUMN
    if two_part:
        q, weight = two_part_target(y, x[:, -1])
        x2, y2, w2 = expand_soft(x[:, :-1], q)
        w2 = w2 * np.concatenate([weight, weight])
        keep = w2 > 0
        x2, y2, w2 = x2[keep], y2[keep], w2[keep]
        model_features = features[:-1]
    else:
        x2, y2, w2 = expand_soft(x, y)
        model_features = features
    model = build(name, params, model_features, seed, constrained)
    if name == "logistic":
        model.fit(x2, y2, logisticregression__sample_weight=w2)
    else:
        model.fit(x2, y2, sample_weight=w2)
    return Fitted(name, model, features, two_part)


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
    constrained: bool = True,
) -> dict[str, Any]:
    """Pick hyperparameters on an inner 80/20 split of the TRAINING data only (Optuna, seeded)."""
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(y))
    cut = int(0.8 * len(y))
    fit_idx, valid_idx = order[:cut], order[cut:]
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    def objective(trial: optuna.Trial) -> float:
        fitted = fit_soft(
            name, suggest(name, trial), x[fit_idx], y[fit_idx], features, seed, constrained
        )
        return scorer(fitted.predict(x[valid_idx]), y[valid_idx])

    study = optuna.create_study(direction="minimize", sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=trials)
    return dict(study.best_params)


def logistic_sign_check(fitted: Fitted) -> list[dict[str, Any]]:
    """Each logistic coefficient (on standardised features) beside the monotone direction the other
    candidates are held to. `agrees` is None where no direction is imposed (direction 0)."""
    coefficients = fitted.model.named_steps["logisticregression"].coef_[0]
    rows = []
    for name, coefficient in zip(fitted.model_features, coefficients, strict=True):
        direction = MONOTONE_DIRECTIONS[name]
        rows.append(
            {
                "feature": name,
                "coefficient": float(coefficient),
                "direction": direction,
                "agrees": None if direction == 0 else bool(np.sign(coefficient) == direction),
            }
        )
    return rows
