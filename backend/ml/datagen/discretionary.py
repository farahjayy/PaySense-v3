"""Discretionary spending (plan P2, A6): week by week, split into merchant-style transactions.

Deliberately RICHER than the forecaster that will be evaluated on it: weekly totals are
over-dispersed and also carry a day-of-week shape, a payday bump, exam-week dips and occasional
very large weeks. A cohort that matched the forecaster's own assumptions would flatter it
(circularity; plan P2 risks), so the generator has structure the models are not told about.
"""

from collections.abc import Collection
from datetime import date, timedelta

import numpy as np

from ml.datagen.calendar import exam_weeks, iter_weeks
from ml.datagen.merchants import describe, describe_refund, describe_transfer
from ml.datagen.params import Params
from ml.datagen.types import Txn

WEEKS_PER_MONTH = 52 / 12
MIN_TXN_SEN = 100  # RM1
MIN_SPLITTABLE_SEN = 300  # a week smaller than this becomes a single transaction
PAYDAY_WINDOW_DAYS = 3
TXN_AMOUNT_SHAPE = 3.0  # gamma shape of transaction sizes within a week (higher = fewer tiny ones)


def _category_shares(params: Params) -> tuple[list[str], np.ndarray]:
    """Share of discretionary *spend* per category (the cited household weights)."""
    food = (
        params["discretionary.category_weight_food"]
        + params["discretionary.category_weight_eating_out"]
    )
    transport = params["discretionary.category_weight_transport"]
    other = params["discretionary.category_other_share"]
    scale = (1 - other) / (food + transport)
    split = {
        "Shopping": params["discretionary.other_split_shopping"],
        "Entertainment": params["discretionary.other_split_entertainment"],
        "Education": params["discretionary.other_split_education"],
    }
    split_total = sum(split.values())
    names = ["Food", "Transport", *split]
    shares = [food * scale, transport * scale, *(other * s / split_total for s in split.values())]
    return names, np.array(shares) / sum(shares)


def _category_sizes(params: Params, names: list[str]) -> np.ndarray:
    return np.array([params[f"discretionary.category_size_weight.{n.lower()}"] for n in names])


def _category_probabilities(params: Params) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Per-transaction category odds and size weights.

    Spend share = odds x typical size, so the odds are the cited spend shares divided by the size
    weights: bigger purchases (shopping) are rarer per transaction, not cheaper per category.
    """
    names, shares = _category_shares(params)
    sizes = _category_sizes(params, names)
    odds = shares / sizes
    return names, odds / odds.sum(), sizes


def _split_exactly(total: int, shares: np.ndarray) -> list[int]:
    """Whole-sen amounts, each at least MIN_TXN_SEN, that sum to exactly `total`."""
    count = len(shares)
    spare = total - MIN_TXN_SEN * count
    raw = shares / shares.sum() * spare
    parts = np.floor(raw).astype(int)
    for index in np.argsort(-(raw - parts))[: spare - int(parts.sum())]:
        parts[index] += 1
    return [int(p) + MIN_TXN_SEN for p in parts]


def _day_weights(days: list[date], income_dates: Collection[date], params: Params) -> np.ndarray:
    dow = params["discretionary.day_of_week_weights"]
    bump = params["discretionary.payday_bump_ratio"]
    weights = []
    for day in days:
        weight = dow[day.weekday()]
        if any(0 <= (day - paid).days < PAYDAY_WINDOW_DAYS for paid in income_dates):
            weight *= 1 + bump
        weights.append(weight)
    return np.array(weights)


def _week_spending(
    params: Params,
    base_week: float,
    monday: date,
    start: date,
    end: date,
    exam: set[date],
    income_dates: Collection[date],
    names: list[str],
    probabilities: np.ndarray,
    sizes: np.ndarray,
    rng: np.random.Generator,
) -> list[Txn]:
    days = [
        monday + timedelta(days=i) for i in range(7) if start <= monday + timedelta(days=i) <= end
    ]
    if not days:
        return []
    sigma = params["discretionary.weekly_sigma"]
    total = base_week * len(days) / 7 * float(np.exp(rng.normal(-(sigma**2) / 2, sigma)))
    if monday in exam:
        total *= 1 - params["discretionary.exam_week_dip_ratio"]
    if rng.random() < params["discretionary.outlier_probability_per_week"]:
        total *= params["discretionary.outlier_multiplier"]
    total_sen = max(int(round(total)), MIN_TXN_SEN)

    wanted = max(
        int(rng.poisson(params["discretionary.transactions_per_week_mean"] * len(days) / 7)), 1
    )
    count = max(1, min(wanted, total_sen // MIN_SPLITTABLE_SEN))
    when = rng.choice(
        len(days),
        size=count,
        p=_day_weights(days, income_dates, params) / _day_weights(days, income_dates, params).sum(),
    )
    chosen = rng.choice(len(names), size=count, p=probabilities)
    amounts = _split_exactly(
        max(total_sen, MIN_TXN_SEN * count),
        rng.gamma(TXN_AMOUNT_SHAPE, size=count) * sizes[chosen],
    )
    miss = params["discretionary.unrecognisable_description_share"]
    out = []
    for day_index, category_index, amount in zip(when, chosen, amounts, strict=True):
        category = names[int(category_index)]
        description = describe(category, rng, recognisable=rng.random() >= miss)
        out.append(Txn(days[int(day_index)], amount, "expense", category, description))
    return out


def _monthly_extras(params: Params, start: date, end: date, rng: np.random.Generator) -> list[Txn]:
    """Occasional refunds and own-account top-ups, so the reserved categories are exercised."""
    out: list[Txn] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        month_days = [
            d
            for d in (cursor + timedelta(days=i) for i in range(31))
            if d.month == cursor.month and start <= d <= end
        ]
        if month_days:
            if rng.random() < params["discretionary.refund_probability_per_month"]:
                day = month_days[int(rng.integers(len(month_days)))]
                out.append(
                    Txn(
                        day,
                        int(rng.integers(2000, 15001)),
                        "income",
                        "Refund",
                        describe_refund(rng),
                    )
                )
            if rng.random() < params["discretionary.transfer_probability_per_month"]:
                day = month_days[int(rng.integers(len(month_days)))]
                out.append(
                    Txn(
                        day,
                        int(rng.integers(2000, 10001)),
                        "expense",
                        "Transfer",
                        describe_transfer(rng),
                    )
                )
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return out


def generate_discretionary(
    params: Params,
    persona: str,
    start: date,
    end: date,
    income_dates: Collection[date],
    rng: np.random.Generator,
) -> list[Txn]:
    """Spending (and the occasional refund / own-account transfer) over [start, end]."""
    level = float(np.exp(rng.normal(0.0, params["discretionary.student_level_sigma"])))
    base_week = params[f"discretionary.monthly_median_sen.{persona}"] * level / WEEKS_PER_MONTH
    exam = exam_weeks(
        start,
        end,
        exam_months=params["discretionary.exam_months"],
        per_semester=params["discretionary.exam_weeks_per_semester"],
    )
    names, probabilities, sizes = _category_probabilities(params)
    txns: list[Txn] = []
    for monday in iter_weeks(start, end):
        txns += _week_spending(
            params,
            base_week,
            monday,
            start,
            end,
            exam,
            income_dates,
            names,
            probabilities,
            sizes,
            rng,
        )
    txns += _monthly_extras(params, start, end, rng)
    txns.sort(key=lambda t: (t.date, t.description, t.amount_sen))
    return txns
