"""Discretionary spending (plan P2, A6): week by week, split into merchant-style transactions.

Deliberately RICHER than the forecaster that will be evaluated on it. At the weekly scale (the
scale the forecasters see) a week's total carries: over-dispersed noise, an AR(1) drift in the
student's spending level, a payday-week lift, exam-week dips and occasional very large weeks.
Day-of-week and payday-day shapes only move spending between days of a week, so they matter for
the transaction list, not for the weekly series. A cohort that matched the forecaster's own
assumptions would flatter it (circularity; plan P2 risks), so the generator has structure the
models are not told about.

A week's total is first divided between categories (Dirichlet around the cited spend shares), then
each category's amount is cut into transactions of that category's typical size. Spend shares are
therefore unbiased, and transaction counts follow from the amounts instead of the reverse.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np

from ml.datagen.calendar import exam_weeks, iter_weeks, week_start
from ml.datagen.merchants import describe, describe_refund, describe_transfer
from ml.datagen.params import Params
from ml.datagen.types import Txn

WEEKS_PER_MONTH = 52 / 12


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


def _between(rng: np.random.Generator, low_high: list[int]) -> int:
    return int(rng.integers(low_high[0], low_high[1] + 1))


def _apportion(total: int, weights: np.ndarray) -> list[int]:
    """Whole-sen parts proportional to `weights` that sum to exactly `total` (largest remainder)."""
    raw = weights / weights.sum() * total
    parts = np.floor(raw).astype(int)
    for index in np.argsort(-(raw - parts), kind="stable")[: total - int(parts.sum())]:
        parts[index] += 1
    return [int(p) for p in parts]


def _split_exactly(total: int, weights: np.ndarray, minimum: int) -> list[int]:
    """Whole-sen amounts, each at least `minimum`, that sum to exactly `total`."""
    spare = total - minimum * len(weights)
    return [minimum + part for part in _apportion(spare, weights)]


@dataclass(frozen=True)
class _Context:
    params: Params
    start: date
    end: date
    exam: set[date]
    income_dates: frozenset[date]
    income_weeks: frozenset[date]
    names: list[str]
    shares: np.ndarray
    typical_sen: np.ndarray
    base_week: float


def _day_weights(days: list[date], ctx: _Context) -> np.ndarray:
    dow = ctx.params["discretionary.day_of_week_weights"]
    bump = ctx.params["discretionary.payday_bump_ratio"]
    window = ctx.params["discretionary.payday_window_days"]
    weights = []
    for day in days:
        weight = dow[day.weekday()]
        if any(day - timedelta(days=back) in ctx.income_dates for back in range(window)):
            weight *= 1 + bump
        weights.append(weight)
    return np.array(weights)


def _week_total(
    ctx: _Context, monday: date, days: int, level: float, rng: np.random.Generator
) -> int:
    params = ctx.params
    sigma = params["discretionary.weekly_sigma"]
    total = ctx.base_week * days / 7 * level
    total *= float(np.exp(rng.normal(-(sigma**2) / 2, sigma)))
    if monday in ctx.exam:
        total *= 1 - params["discretionary.exam_week_dip_ratio"]
    if monday in ctx.income_weeks:
        total *= 1 + params["discretionary.payday_week_total_bump_ratio"]
    if rng.random() < params["discretionary.outlier_probability_per_week"]:
        total *= params["discretionary.outlier_multiplier"]
    return max(int(round(total)), params["discretionary.min_txn_sen"])


def _category_amounts(ctx: _Context, total: int, rng: np.random.Generator) -> list[int]:
    """Split a week's total between categories.

    A category whose expected weekly spend is below its typical purchase is present only some
    weeks (probability expected / typical) and then spends about a typical purchase, so shopping
    is an occasional RM60 item, not a RM10 one every week. Dividing by that probability, and not
    rescaling to the week's drawn total, keeps each category's spend share (and the total's mean)
    unbiased; the week's realised total is therefore slightly noisier than the drawn one.
    """
    minimum = ctx.params["discretionary.min_txn_sen"]
    concentration = ctx.params["discretionary.category_allocation_concentration"]
    noise = rng.dirichlet(ctx.shares * concentration)
    presence = np.minimum(1.0, ctx.shares * total / ctx.typical_sen)
    present = rng.random(len(presence)) < presence
    present[int(np.argmax(ctx.shares))] = True
    weights = np.where(present, noise / presence, 0.0)
    amounts = [int(round(total * w)) for w in weights]  # unnormalised: mean is `total`
    biggest = int(np.argmax(amounts))
    for index, amount in enumerate(amounts):
        if index != biggest and 0 < amount < minimum:
            amounts[biggest] += amount
            amounts[index] = 0
    return amounts


def _week_spending(
    ctx: _Context, monday: date, level: float, rng: np.random.Generator
) -> list[Txn]:
    params = ctx.params
    days = [
        monday + timedelta(days=i)
        for i in range(7)
        if ctx.start <= monday + timedelta(days=i) <= ctx.end
    ]
    if not days:
        return []
    minimum = params["discretionary.min_txn_sen"]
    day_weights = _day_weights(days, ctx)
    day_probabilities = day_weights / day_weights.sum()
    miss = params["discretionary.unrecognisable_description_share"]
    out = []
    amounts = _category_amounts(ctx, _week_total(ctx, monday, len(days), level, rng), rng)
    for index, amount in enumerate(amounts):
        if amount <= 0:
            continue
        typical = ctx.typical_sen[index]
        floor = min(
            max(minimum, int(typical * params["discretionary.min_txn_share_of_typical"])), amount
        )
        count = int(max(1, min(round(amount / typical), amount // floor)))
        parts = _split_exactly(
            amount, rng.gamma(params["discretionary.txn_amount_gamma_shape"], size=count), floor
        )
        when = rng.choice(len(days), size=count, p=day_probabilities)
        category = ctx.names[index]
        for day_index, part in zip(when, parts, strict=True):
            description = describe(category, rng, recognisable=rng.random() >= miss)
            out.append(Txn(days[int(day_index)], part, "expense", category, description))
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
                        _between(rng, params["discretionary.refund_amount_sen_range"]),
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
                        _between(rng, params["discretionary.transfer_amount_sen_range"]),
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
    names, shares = _category_shares(params)
    phi = params["discretionary.weekly_ar1_phi"]
    sigma = params["discretionary.weekly_ar1_sigma"]
    ctx = _Context(
        params=params,
        start=start,
        end=end,
        exam=exam_weeks(
            start,
            end,
            exam_months=params["discretionary.exam_months"],
            per_semester=params["discretionary.exam_weeks_per_semester"],
        ),
        income_dates=frozenset(income_dates),
        income_weeks=frozenset(week_start(d) for d in income_dates),
        names=names,
        shares=shares,
        typical_sen=np.array(
            [params[f"discretionary.category_typical_txn_sen.{n.lower()}"] for n in names]
        ),
        base_week=params[f"discretionary.monthly_median_sen.{persona}"] * level / WEEKS_PER_MONTH,
    )
    stationary_var = sigma**2 / (1 - phi**2)
    drift = float(rng.normal(0.0, np.sqrt(stationary_var)))
    txns: list[Txn] = []
    for monday in iter_weeks(start, end):
        drift = phi * drift + sigma * float(rng.normal())
        week_level = float(np.exp(drift - stationary_var / 2))  # mean one, so levels are preserved
        txns += _week_spending(ctx, monday, week_level, rng)
    txns += _monthly_extras(params, start, end, rng)
    txns.sort(key=lambda t: (t.date, t.description, t.amount_sen))
    return txns
