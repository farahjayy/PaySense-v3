"""Facts about the label distribution, shared by training (results.json) and the report.

How much of a label is the student's baseline (the simulated shortfall chance WITHOUT the purchase)
and how much is the purchase, whether the labels saturate at 0 or 1, and the Monte Carlo noise
floor of any Brier score computed against them.
"""

import numpy as np

from ml.engine2_train.data import Dataset
from ml.engine2_train.metrics import band_index

SAFE_EDGE = 0.10  # pre-registered: Safe < 0.10
STOP_RULE_SHARE = 0.85  # execution doc D4: stop if more labels than this sit within the margin
STOP_RULE_MARGIN = 0.02  # of exactly 0 or 1
NEAR = 0.01  # "the purchase changes the label by less than this"


def baseline_facts(data: Dataset, paths: int | None) -> dict[str, float | None]:
    """How much of the label is the student's baseline and how much is the purchase."""
    y, base = data.y, data.p_without
    facts: dict[str, float | None] = {
        "share_label_exactly_0": float((y == 0).mean()),
        "share_label_exactly_1": float((y == 1).mean()),
        "share_label_within_stop_margin": float(
            ((y < STOP_RULE_MARGIN) | (y > 1 - STOP_RULE_MARGIN)).mean()
        ),
        "monte_carlo_noise_floor_brier": float(np.mean(y * (1 - y)) / paths) if paths else None,
    }
    if base is not None:
        moved = band_index(y) != band_index(base)
        facts |= {
            "share_p_without_exactly_0": float((base == 0).mean()),
            "share_p_without_exactly_1": float((base == 1).mean()),
            "share_p_without_below_safe_edge": float((base < SAFE_EDGE).mean()),
            "share_p_without_at_or_above_safe_edge": float((base >= SAFE_EDGE).mean()),
            "share_purchase_moves_the_band": float(moved.mean()),
            "share_purchase_changes_label_by_under_001": float((y - base < NEAR).mean()),
        }
    return facts
