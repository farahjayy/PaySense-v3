"""The winner rule, written down before any training (plan P5 execution doc).

The winner is the candidate with the lowest mean Brier score under the grouped 5x5 CV, unless a
SIMPLER candidate is within one standard error of it and not significantly worse by the corrected
resampled t-test (Holm-adjusted over the comparisons), in which case the simpler one is served and
that is reported. "Simpler" follows `CANDIDATES`: logistic, LightGBM, XGBoost, random forest.
"""

from dataclasses import dataclass

from ml.engine2_train.cv import CvResult, nadeau_bengio
from ml.engine2_train.models import CANDIDATES

SIGNIFICANCE = 0.05


@dataclass(frozen=True)
class Choice:
    winner: str
    best_by_brier: str
    reason: str
    brier: dict[str, float]
    p_values: dict[str, float]  # simpler candidate vs the best, Holm-adjusted


def _holm(p_values: list[float]) -> list[float]:
    order = sorted(range(len(p_values)), key=lambda i: p_values[i])
    adjusted, running = [0.0] * len(p_values), 0.0
    for rank, index in enumerate(order):
        running = max(running, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[index] = running
    return adjusted


def choose(results: dict[str, CvResult]) -> Choice:
    scores = {name: r.mean("brier") for name, r in results.items()}
    best = min(scores, key=scores.get)
    simpler = [c for c in CANDIDATES[: CANDIDATES.index(best)] if c in results]
    tests = {c: nadeau_bengio(results[c], results[best])[2] for c in simpler}
    adjusted = dict(zip(tests, _holm(list(tests.values())), strict=True))
    se = results[best].standard_error("brier")
    for name in simpler:  # simplest first
        close = scores[name] - scores[best] <= se
        if close and adjusted[name] >= SIGNIFICANCE:
            return Choice(
                name, best, f"{name} is within one SE of {best} and not significantly worse",
                scores, adjusted,
            )  # fmt: skip
    return Choice(best, best, "lowest mean Brier score", scores, adjusted)
