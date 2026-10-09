"""Exact Shapley values of a model's output against one reference student (ADR D-40).

For an input `x` and a reference `b`, a coalition S of features takes their value from `x` and the
rest from `b`. The Shapley value of feature i is its average marginal effect over all orders in
which features can be added. It is computed exactly, from the model's own output (so it is on the
same scale as the number a student sees, calibration included), with no approximation and no model
internals: every coalition of the features that differ goes through the model in one batch.

A feature that already equals the reference contributes exactly 0 and is left out of the
coalitions, so the batch is at most 2**16 = 65,536 rows for the 16 Engine 2 features.
"""

from collections.abc import Callable
from math import factorial

import numpy as np

Model = Callable[[np.ndarray], np.ndarray]


def baseline_shapley(model: Model, x: np.ndarray, baseline: np.ndarray) -> np.ndarray:
    """`model` maps a (rows, features) array to (rows,) outputs. Returns one value per feature;
    they add up to `model(x) - model(baseline)`."""
    x = np.asarray(x, dtype=float)
    baseline = np.asarray(baseline, dtype=float)
    if x.shape != baseline.shape or x.ndim != 1:
        raise ValueError("x and baseline must be vectors of the same length")
    active = np.flatnonzero(x != baseline)
    contributions = np.zeros(len(x))
    m = len(active)
    if m == 0:
        return contributions

    coalitions = np.arange(2**m)
    bits = ((coalitions[:, None] >> np.arange(m)) & 1).astype(bool)  # (2**m, m)
    batch = np.tile(baseline, (2**m, 1))
    batch[:, active] = np.where(bits, x[active], baseline[active])
    values = np.asarray(model(batch), dtype=float)

    size = bits.sum(axis=1)
    weights = np.array([factorial(k) * factorial(m - k - 1) / factorial(m) for k in range(m)])
    for position, feature in enumerate(active):
        without = coalitions[~bits[:, position]]
        gain = values[without | (1 << position)] - values[without]
        contributions[feature] = float((weights[size[without]] * gain).sum())
    return contributions
