"""ml-audit M2: the fresh check uses students nobody fitted, chose or tested anything on."""

import numpy as np

from ml.engine1_eval.band_calibration import (
    COHORT,
    DEV_PROFILES,
    EVAL_POOL,
    GRID,
    Record,
    dev_profiles,
)
from ml.engine1_eval.band_calibration import test_profiles as heldout_profiles
from ml.engine1_eval.band_fresh_check import fresh_profiles, render, served_factor


def test_fresh_students_are_disjoint_from_every_group_already_used():
    fresh = fresh_profiles()
    assert len(fresh) == len(set(fresh)) == 300
    assert not set(fresh) & set(dev_profiles(DEV_PROFILES))
    assert not set(fresh) & set(heldout_profiles())
    assert all(EVAL_POOL <= i < COHORT and i % 10 != 0 for i in fresh)
    assert fresh == fresh_profiles()  # seeded


def _record(kind, weeks, inside_at):
    inside = np.zeros(len(GRID), dtype=bool)
    inside[[GRID.index(f) for f in inside_at]] = True
    return Record(4001, kind, weeks, False, inside, inside.copy(), 0.0, 0.0)


def test_the_report_scores_the_served_factor_beside_the_v2_rule():
    rec = _record("spend", 30, [served_factor(_record("spend", 30, []))])
    page = render([rec, _record("income", 60, [1.5])], [4001])
    assert "do not edit by hand" in page
    assert "| spend | 26-38 | 1 | 0.00 |" in page  # inside only at the served factor, not at 1.5
    assert page.count("| income |") == 5
