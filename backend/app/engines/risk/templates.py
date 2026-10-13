"""Plain-language sentences for the features that push a risk check up (D-12).

One template per feature. A sentence is built only from that feature's own value, rounded in one
place (`_rm`, `_pct`, `_months`), so a number on screen can always be traced to the feature vector
and nowhere else. `figures` lists exactly what was printed; the tests recompute them independently.
Which features to mention is decided elsewhere (SHAP, threshold 0.02); this module only words them.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass

MANY_INSTALMENTS = 6  # at or above this, the plan's length is the point; below, the size of each


@dataclass(frozen=True)
class Factor:
    feature: str
    text: str
    figures: tuple[str, ...]


def _half_up(x: float) -> int:
    if not math.isfinite(x):
        raise ValueError(f"a sentence needs a finite number, got {x!r}")
    return int(abs(x) + 0.5)


def _rm(x: float) -> str:
    """Whole ringgit, thousands separated; a negative amount keeps its sign: -RM 311."""
    text = f"RM {_half_up(x):,}"
    return f"-{text}" if x < 0 and _half_up(x) else text


def _pct(ratio: float) -> str:
    return str(_half_up(ratio * 100))


def _months(ratio: float) -> str:
    return f"{_half_up(ratio * 10) / 10:.1f}"


def _plain(x: float) -> str:
    """A number without trailing zeros: 1.5, 2, 0.25."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def _figures(*parts: str) -> tuple[str, ...]:
    return tuple(p.replace("RM ", "").replace("-", "").replace(",", "") for p in parts)


Builder = Callable[[Mapping[str, float]], Factor | None]


def _simple(feature: str, pattern: str, fmt: Callable[[float], str]) -> Builder:
    def build(values: Mapping[str, float]) -> Factor:
        shown = fmt(values[feature])
        return Factor(feature, pattern.format(shown), _figures(shown))

    return build


def _margin_monthly(values: Mapping[str, float]) -> Factor:
    value = values["margin_monthly_p50_without"]
    shown = _rm(abs(value))
    if value < 0:
        text = f"Even before this purchase, you are about {shown} short each month."
    else:
        text = f"Before this purchase you are left with only about {shown} each month."
    return Factor("margin_monthly_p50_without", text, _figures(shown))


def _num_instalments(values: Mapping[str, float]) -> Factor:
    count = _half_up(values["num_instalments"])
    if count >= MANY_INSTALMENTS:
        text = f"The plan runs for {count} instalments, so you carry the commitment for longer."
    elif count == 1:
        text = "The whole amount is a single payment, so it is all due at once."
    else:
        text = f"The plan has only {count} instalments, so each one is larger."
    return Factor("num_instalments", text, (str(count),))


def _active_plans(values: Mapping[str, float]) -> Factor:
    count = _half_up(values["active_plans_with_purchase"])
    if count == 1:
        text = "This would be your only BNPL plan."
    else:
        text = f"You would have {count} active BNPL plans at the same time."
    return Factor("active_plans_with_purchase", text, (str(count),))


def _fee(values: Mapping[str, float]) -> Factor:
    shown = _plain(values["monthly_fee_rate"])
    return Factor("monthly_fee_rate", f"The provider charges a monthly fee of {shown}%.", (shown,))


def _limit_known(values: Mapping[str, float]) -> Factor | None:
    if values["limit_known"] >= 0.5:
        return None
    return Factor(
        "limit_known",
        "You have not recorded a limit with this provider, so we cannot see how much room you "
        "have left.",
        (),
    )


TEMPLATES: dict[str, Builder] = {
    "disc_weekly_p50": _simple(
        "disc_weekly_p50", "Your everyday spending is about {} a week.", _rm
    ),
    "disc_weekly_p90": _simple(
        "disc_weekly_p90", "In a heavy week you spend about {} on everyday things.", _rm
    ),
    "disc_volatility": _simple(
        "disc_volatility", "Your weekly spending swings by about {} from week to week.", _rm
    ),
    "margin_monthly_p50_without": _margin_monthly,
    "margin_cum_p10_without": _simple(
        "margin_cum_p10_without",
        "In a bad run of months your running margin could fall to about {} before this purchase.",
        _rm,
    ),
    "income_p10_monthly": _simple(
        "income_p10_monthly", "In a weak month your income could be as low as about {}.", _rm
    ),
    "instalment_amount": _simple("instalment_amount", "Each instalment is about {}.", _rm),
    "num_instalments": _num_instalments,
    "monthly_fee_rate": _fee,
    "instalment_to_income": _simple(
        "instalment_to_income", "Each instalment is about {}% of your monthly income.", _pct
    ),
    "dsr_with_purchase": _simple(
        "dsr_with_purchase",
        "With this plan, about {}% of your monthly income would go on BNPL and similar repayments.",
        _pct,
    ),
    "active_plans_with_purchase": _active_plans,
    "bnpl_outstanding_to_income": _simple(
        "bnpl_outstanding_to_income",
        "You would owe about {} months of your income across BNPL plans.",
        _months,
    ),
    "upfront_to_income": _simple(
        "upfront_to_income", "You would pay about {}% of a month's income at checkout.", _pct
    ),
    "limit_utilisation_with_purchase": _simple(
        "limit_utilisation_with_purchase", "This would use about {}% of your recorded limit.", _pct
    ),
    "limit_known": _limit_known,
}


def render_factor(feature: str, values: Mapping[str, float]) -> Factor | None:
    """The sentence for one feature, or None when it has nothing to say for these values.

    Raises KeyError for an unknown feature or a value that is missing: never a guess.
    """
    return TEMPLATES[feature](values)
