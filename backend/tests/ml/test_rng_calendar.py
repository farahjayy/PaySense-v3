from datetime import date

import numpy as np
import pytest

from ml.datagen.calendar import (
    day_in_month,
    exam_weeks,
    iter_month_starts,
    iter_weeks,
    week_start,
)
from ml.datagen.rng import profile_rng


# ------------------------------------------------------------------ rng
def draws(rng, n=5):
    return rng.random(n).tolist()


def test_the_same_seed_index_and_stream_always_give_the_same_numbers():
    assert draws(profile_rng(42, 7, "income")) == draws(profile_rng(42, 7, "income"))


def test_different_profiles_get_different_streams():
    assert draws(profile_rng(42, 7, "income")) != draws(profile_rng(42, 8, "income"))


def test_different_master_seeds_differ():
    assert draws(profile_rng(1, 0, "income")) != draws(profile_rng(2, 0, "income"))


def test_named_streams_are_independent_so_editing_one_component_cannot_shift_another():
    bills_alone = draws(profile_rng(42, 3, "bills"))

    income = profile_rng(42, 3, "income")
    income.random(1000)  # a component that suddenly draws far more numbers
    bills_after = draws(profile_rng(42, 3, "bills"))

    assert bills_alone == bills_after
    assert draws(profile_rng(42, 3, "income")) != draws(profile_rng(42, 3, "bills"))


def test_profile_n_is_the_same_whether_one_or_many_profiles_are_generated():
    many = [draws(profile_rng(9, i, "x")) for i in range(100)]
    few = [draws(profile_rng(9, i, "x")) for i in range(10)]

    assert many[:10] == few


def test_it_returns_a_numpy_generator():
    assert isinstance(profile_rng(1, 0, "x"), np.random.Generator)


@pytest.mark.parametrize("bad", [(-1, 0), (0, -1)])
def test_negative_seeds_and_indices_are_refused(bad):
    with pytest.raises(ValueError):
        profile_rng(bad[0], bad[1], "x")


# ------------------------------------------------------------------ calendar
def test_week_start_is_the_monday():
    assert week_start(date(2026, 3, 4)) == date(2026, 3, 2)  # Wednesday
    assert week_start(date(2026, 3, 2)) == date(2026, 3, 2)  # already Monday
    assert week_start(date(2026, 3, 8)) == date(2026, 3, 2)  # Sunday


def test_iter_weeks_lists_every_monday_from_the_first_to_the_last_covering_the_range():
    weeks = list(iter_weeks(date(2026, 3, 4), date(2026, 3, 17)))

    assert weeks == [date(2026, 3, 2), date(2026, 3, 9), date(2026, 3, 16)]


def test_iter_weeks_of_a_single_day_is_that_days_week():
    assert list(iter_weeks(date(2026, 3, 4), date(2026, 3, 4))) == [date(2026, 3, 2)]


def test_iter_month_starts_covers_each_calendar_month_in_range():
    months = list(iter_month_starts(date(2026, 1, 20), date(2026, 4, 2)))

    assert months == [date(2026, 1, 1), date(2026, 2, 1), date(2026, 3, 1), date(2026, 4, 1)]


def test_iter_month_starts_crosses_a_year_boundary():
    months = list(iter_month_starts(date(2025, 11, 5), date(2026, 2, 5)))

    assert months == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


@pytest.mark.parametrize(
    ("year", "month", "day", "expected"),
    [
        (2026, 2, 30, date(2026, 2, 28)),
        (2024, 2, 30, date(2024, 2, 29)),
        (2026, 4, 31, date(2026, 4, 30)),
        (2026, 1, 31, date(2026, 1, 31)),
        (2026, 6, 1, date(2026, 6, 1)),
    ],
)
def test_day_in_month_clamps_to_the_last_valid_day(year, month, day, expected):
    assert day_in_month(year, month, day) == expected


def test_exam_weeks_are_the_last_k_weeks_of_each_exam_month():
    weeks = exam_weeks(date(2026, 5, 1), date(2026, 7, 31), exam_months=(6,), per_semester=2)

    # June 2026 has five Mondays (1, 8, 15, 22, 29); the last two are the exam weeks.
    june_mondays = [
        date(2026, 6, 1),
        date(2026, 6, 8),
        date(2026, 6, 15),
        date(2026, 6, 22),
        date(2026, 6, 29),
    ]
    assert weeks == set(june_mondays[-2:])


def test_exam_weeks_in_a_range_without_exam_months_is_empty():
    assert (
        exam_weeks(date(2026, 2, 1), date(2026, 3, 31), exam_months=(6, 12), per_semester=2)
        == set()
    )


def test_zero_exam_weeks_per_semester_means_no_exam_weeks():
    assert (
        exam_weeks(date(2025, 6, 1), date(2025, 6, 30), exam_months=(6,), per_semester=0) == set()
    )


def test_a_negative_exam_length_is_rejected():
    import pytest

    with pytest.raises(ValueError, match="per_semester"):
        exam_weeks(date(2025, 6, 1), date(2025, 6, 30), exam_months=(6,), per_semester=-1)
