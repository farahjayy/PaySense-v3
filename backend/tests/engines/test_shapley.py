"""Exact Shapley values against a baseline student: the explanation method (ADR D-40)."""

import itertools
from math import factorial

import numpy as np
import pytest

from app.engines.risk.shapley import baseline_shapley


def brute_force(f, x, baseline):
    """The definition, one subset at a time, for small problems."""
    n = len(x)
    out = np.zeros(n)
    for i in range(n):
        others = [j for j in range(n) if j != i]
        for size in range(n):
            for subset in itertools.combinations(others, size):
                without = baseline.copy()
                without[list(subset)] = x[list(subset)]
                with_i = without.copy()
                with_i[i] = x[i]
                weight = factorial(size) * factorial(n - size - 1) / factorial(n)
                out[i] += weight * (f(with_i[None, :])[0] - f(without[None, :])[0])
    return out


def sigmoid(z):
    return 1 / (1 + np.exp(-z))


def interaction(batch):
    """Not additive: a product term makes the split between features non-trivial."""
    a, b, c, d = batch.T
    return sigmoid(0.8 * a - 0.5 * b + 1.5 * a * c + 0.3 * d * d)


X = np.array([1.2, -0.4, 0.9, 2.0])
B = np.array([0.0, 0.5, -0.2, 1.0])


def test_matches_the_definition_on_a_function_with_interactions():
    got = baseline_shapley(interaction, X, B)
    assert got == pytest.approx(brute_force(interaction, X, B), abs=1e-12)


def test_contributions_add_up_to_the_change_from_the_baseline():
    got = baseline_shapley(interaction, X, B)
    expected = interaction(X[None, :])[0] - interaction(B[None, :])[0]
    assert got.sum() == pytest.approx(expected, abs=1e-12)


def test_a_feature_equal_to_the_baseline_contributes_exactly_nothing():
    x = X.copy()
    x[2] = B[2]
    got = baseline_shapley(interaction, x, B)
    assert got[2] == 0.0
    assert got == pytest.approx(brute_force(interaction, x, B), abs=1e-12)


def test_a_purely_additive_function_gives_each_feature_its_own_term():
    def linear(batch):
        return batch @ np.array([0.5, -1.0, 2.0, 0.0])

    got = baseline_shapley(linear, X, B)
    assert got == pytest.approx((X - B) * np.array([0.5, -1.0, 2.0, 0.0]))


def test_identical_input_and_baseline_give_all_zeros_without_calling_the_model():
    calls = []

    def f(batch):
        calls.append(len(batch))
        return batch.sum(axis=1)

    assert not baseline_shapley(f, B, B).any()
    assert calls == []


def test_the_model_is_called_once_with_every_coalition_of_the_features_that_differ():
    sizes = []

    def f(batch):
        sizes.append(batch.shape)
        return batch.sum(axis=1)

    x = X.copy()
    x[0] = B[0]  # three features differ -> 2**3 coalitions
    baseline_shapley(f, x, B)
    assert sizes == [(8, 4)]


def test_sixteen_features_are_a_single_batch_of_65536_rows():
    rng = np.random.default_rng(0)
    w = rng.normal(size=16)
    x, b = rng.normal(size=16), rng.normal(size=16)
    shapes = []

    def f(batch):
        shapes.append(batch.shape)
        return sigmoid(batch @ w)

    got = baseline_shapley(f, x, b)
    assert shapes == [(65536, 16)]
    assert got.sum() == pytest.approx(f(x[None, :])[0] - f(b[None, :])[0], abs=1e-9)


def test_a_mismatched_pair_of_vectors_is_an_error():
    with pytest.raises(ValueError):
        baseline_shapley(interaction, X, B[:3])


def test_too_many_differing_features_is_refused_before_it_allocates_the_batch():
    from app.engines.risk.shapley import MAX_ACTIVE

    n = MAX_ACTIVE + 1
    with pytest.raises(ValueError, match="features differ"):
        baseline_shapley(lambda rows: rows.sum(axis=1), np.ones(n), np.zeros(n))


def test_a_nan_input_is_refused():
    with pytest.raises(ValueError, match="finite"):
        baseline_shapley(lambda rows: rows.sum(axis=1), np.array([np.nan, 1.0]), np.zeros(2))
