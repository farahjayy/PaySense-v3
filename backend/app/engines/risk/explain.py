"""Which reasons to show for a risk check (ADR D-12).

SHAP-style contributions say how much each feature pushed this student's probability up or down.
Only features that push it UP by at least `FACTOR_THRESHOLD` are reasons; the largest come first,
at most `MAX_FACTORS`. Each is worded by its own template from its own value (`templates.py`), so a
sentence can never mention a feature that did not qualify or a number that is not that feature's.
Nothing qualifying is a valid answer: the screen says "nothing stands out".
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.engines.risk.features import FEATURE_NAMES
from app.engines.risk.templates import render_factor

FACTOR_THRESHOLD = 0.02  # contribution to the probability, on the same 0-1 scale
MAX_FACTORS = 5


@dataclass(frozen=True)
class ExplainedFactor:
    feature: str
    text: str
    figures: tuple[str, ...]
    contribution: float


def select_factors(
    values: Mapping[str, float], contributions: Sequence[float]
) -> list[ExplainedFactor]:
    """`contributions` are in `FEATURE_NAMES` order."""
    if len(contributions) != len(FEATURE_NAMES):
        raise ValueError(f"expected {len(FEATURE_NAMES)} contributions, got {len(contributions)}")
    ranked = sorted(
        (
            (name, c)
            for name, c in zip(FEATURE_NAMES, contributions, strict=True)
            if c >= FACTOR_THRESHOLD
        ),
        key=lambda pair: pair[1],
        reverse=True,
    )
    out: list[ExplainedFactor] = []
    for name, contribution in ranked:
        factor = render_factor(name, values)
        if factor is None:  # the template has nothing to say for these values
            continue
        out.append(ExplainedFactor(name, factor.text, factor.figures, float(contribution)))
        if len(out) == MAX_FACTORS:
            break
    return out
