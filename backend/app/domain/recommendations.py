"""Ranked recommendations and proactive alerts (WP15).

A fixed, ordered rule set over outputs the app already computes: Engine 1's forecast, budget status
(WP2), bill analysis (WP13), spending insights (WP14) and provider limits. No model and no free
text: every sentence is built from the recommendation's own `sources`, so each figure on screen
can be traced to the tool that produced it (a test checks every number). An action is a link to a
screen or a pre-filled proposal that still needs the person's confirmation (ADR D-48).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Literal

from app.domain.money import format_rm
from app.engines.forecasting.simulate import CAUTION_BELOW, SAFE_BELOW

Severity = Literal["high", "medium", "low"]
Unit = Literal["sen", "percent", "probability", "count", "date", "text"]

NEAR_SHARE = 0.8  # a provider limit this used is "nearly used" (same edge as a budget, WP2)
SOON_DAYS = 7  # a collision starting within this many days is an alert
UP_SHARE = 0.20  # the spending-up rule: the same edges as the insights headline (WP14)
UP_MIN_SEN = 5_000
PER_RULE = 3  # at most this many recommendations from one rule
PROVIDER_LABELS = {"spaylater": "SPayLater", "tiktok_paylater": "TikTok PayLater", "atome": "Atome"}
# ASSUMED 25 (WP15): "shortfall chance above the Caution edge" is read as the At Risk band.
RULES = (
    "forecast_shortfall",
    "budget_over",
    "bill_collision",
    "budget_near",
    "plan_near_limit",
    "bill_increase",
    "spending_up",
    "forecast_locked",
    "no_budgets",
)


@dataclass(frozen=True)
class Source:
    label: str
    value: int | float | str
    unit: Unit
    source: str


@dataclass(frozen=True)
class Action:
    kind: Literal["link", "propose"]
    label: str
    href: str | None = None
    action_type: Literal["set_budget"] | None = None
    payload: dict[str, str | int] | None = None


@dataclass(frozen=True)
class Recommendation:
    rule: str
    priority: int
    severity: Severity
    title: str
    detail: str
    sources: list[Source]
    action: Action | None
    is_alert: bool = False


@dataclass(frozen=True)
class Inputs:
    today: date
    forecast: Mapping[str, Any]
    budget_status: Mapping[str, Any]
    budgets: Sequence[Mapping[str, Any]]
    bills: Mapping[str, Any]
    insights: Mapping[str, Any]
    limits: Sequence[Mapping[str, Any]]
    notes: list[str] = field(default_factory=list)


def _day(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _short(value: date | str) -> str:
    day = _day(value)
    return f"{day.day} {day.strftime('%b')}"


def _month_name(key: str) -> str:
    return date(int(key[:4]), int(key[5:7]), 1).strftime("%B %Y")


def _pct(ratio: float) -> str:
    return f"{round(ratio * 100)}%"


def format_source(source: Source) -> str:
    """How a source figure is written in a sentence (the trace test reads this)."""
    if source.unit == "sen":
        return format_rm(int(source.value))
    if source.unit in ("percent", "probability"):
        return _pct(float(source.value))
    if source.unit == "date":
        day = _day(source.value)
        return f"{_short(day)} {day.year}"
    return str(source.value)


def _rule(name: str) -> int:
    return RULES.index(name) + 1


def _forecast(inputs: Inputs) -> list[Recommendation]:
    f = inputs.forecast
    if f.get("status") != "ok":
        months = int(f.get("months_of_history") or 0)
        return [
            Recommendation(
                rule="forecast_locked",
                priority=_rule("forecast_locked"),
                severity="low",
                title="Add more history to unlock the forecast",
                detail=f"The forecast needs four months of history; you have {months}.",
                sources=[Source("Months of history", months, "count", "get_forecast")],
                action=Action("link", "Import a statement", href="/import"),
            )
        ]
    p = float(f["simulation"]["p_shortfall"])
    if p < SAFE_BELOW:
        return []
    at_risk = p >= CAUTION_BELOW
    worst = f["simulation"].get("worst_month")
    sources = [
        Source("Chance of a shortfall", p, "probability", "get_forecast"),
        Source("Band", f.get("band") or "", "text", "get_forecast"),
    ]
    detail = (
        f"The forecast gives a {_pct(p)} chance that your running margin falls below zero "
        "in the next three months"
    )
    if worst:
        sources.append(Source("Tightest month", _month_name(worst), "text", "get_forecast"))
        detail += f", tightest in {_month_name(worst)}"
    return [
        Recommendation(
            rule="forecast_shortfall",
            priority=_rule("forecast_shortfall"),
            severity="high" if at_risk else "medium",
            title="Your money may run short" if at_risk else "Money looks tight ahead",
            detail=detail + ".",
            sources=sources,
            action=Action("link", "See the forecast", href="/"),
            is_alert=at_risk,
        )
    ]


def _budgets(inputs: Inputs) -> list[Recommendation]:
    out: list[Recommendation] = []
    items = inputs.budget_status.get("items", [])
    for item in [i for i in items if i["state"] == "over"][:PER_RULE]:
        out.append(
            Recommendation(
                rule="budget_over",
                priority=_rule("budget_over"),
                severity="high",
                title=f"{item['category']} is over budget",
                detail=(
                    f"You have spent {format_rm(item['spent_sen'])} of your "
                    f"{format_rm(item['limit_sen'])} {item['category']} budget this month."
                ),
                sources=[
                    Source("Spent", item["spent_sen"], "sen", "get_budget_status"),
                    Source("Limit", item["limit_sen"], "sen", "get_budget_status"),
                ],
                action=Action("link", "Review budgets", href="/budgets"),
                is_alert=True,
            )
        )
    near = [
        i
        for i in items
        if i["state"] == "near" or (i["state"] == "ok" and i.get("projected_state") == "over")
    ]
    for item in near[:PER_RULE]:
        sources = [
            Source("Spent", item["spent_sen"], "sen", "get_budget_status"),
            Source("Limit", item["limit_sen"], "sen", "get_budget_status"),
        ]
        detail = f"{format_rm(item['spent_sen'])} spent of {format_rm(item['limit_sen'])}"
        if item.get("projected_sen") is not None:
            sources.append(
                Source("At this pace", item["projected_sen"], "sen", "get_budget_status")
            )
            detail += f"; at this pace about {format_rm(item['projected_sen'])} by the month end"
        out.append(
            Recommendation(
                rule="budget_near",
                priority=_rule("budget_near"),
                severity="medium",
                title=f"{item['category']} is close to its budget",
                detail=detail + ".",
                sources=sources,
                action=Action("link", "Review budgets", href="/budgets"),
            )
        )
    return out


def _collisions(inputs: Inputs) -> list[Recommendation]:
    out = []
    soon_until = inputs.today + timedelta(days=SOON_DAYS - 1)
    for c in inputs.bills.get("collisions", [])[:PER_RULE]:
        soon = _day(c["start"]) <= soon_until
        count = len(c["items"])
        names = ", ".join(i["name"] for i in c["items"])
        out.append(
            Recommendation(
                rule="bill_collision",
                priority=_rule("bill_collision"),
                severity="high" if soon else "medium",
                title=f"{count} payments fall in the same week",
                detail=(
                    f"{format_rm(c['total_sen'])} is due between {_short(c['start'])} and "
                    f"{_short(c['end'])}: {names}."
                ),
                sources=[
                    Source("Due in that week", c["total_sen"], "sen", "get_bill_analysis"),
                    Source("Payments", count, "count", "get_bill_analysis"),
                    Source("From", _day(c["start"]).isoformat(), "date", "get_bill_analysis"),
                    Source("To", _day(c["end"]).isoformat(), "date", "get_bill_analysis"),
                ],
                action=Action("link", "See your plans", href="/plans"),
                is_alert=soon,
            )
        )
    return out


def _limits(inputs: Inputs) -> list[Recommendation]:
    out = []
    for row in inputs.limits:
        limit, used = row.get("limit_sen"), int(row.get("used_sen") or 0)
        if not limit or used / limit < NEAR_SHARE:
            continue
        label = PROVIDER_LABELS.get(row["provider"], row["provider"])
        out.append(
            Recommendation(
                rule="plan_near_limit",
                priority=_rule("plan_near_limit"),
                severity="medium",
                title=f"Your {label} limit is nearly used",
                detail=f"{format_rm(used)} of your {format_rm(limit)} {label} limit is in use.",
                sources=[
                    Source("In use", used, "sen", "list_providers_and_limits"),
                    Source("Limit", int(limit), "sen", "list_providers_and_limits"),
                ],
                action=Action("link", "See your plans", href="/plans"),
            )
        )
    return out[:PER_RULE]


def _increases(inputs: Inputs) -> list[Recommendation]:
    return [
        Recommendation(
            rule="bill_increase",
            priority=_rule("bill_increase"),
            severity="medium",
            title=f"{inc['name']} went up {format_rm(inc['change_sen'])}",
            detail=(
                f"It was {format_rm(inc['previous_sen'])} and is now "
                f"{format_rm(inc['latest_sen'])}."
            ),
            sources=[
                Source("Before", inc["previous_sen"], "sen", "get_bill_analysis"),
                Source("Now", inc["latest_sen"], "sen", "get_bill_analysis"),
                Source("Increase", inc["change_sen"], "sen", "get_bill_analysis"),
            ],
            action=Action("link", "See recurring items", href="/recurring"),
        )
        for inc in inputs.bills.get("increases", [])[:PER_RULE]
    ]


def _spending_up(inputs: Inputs) -> list[Recommendation]:
    ups = [
        m
        for m in inputs.insights.get("movers", [])
        if m["status"] == "up"
        and m.get("change_pct") is not None
        and m["change_pct"] >= UP_SHARE
        and m["change_sen"] >= UP_MIN_SEN
    ]
    if not ups:
        return []
    top = max(ups, key=lambda m: m["change_sen"])
    category, before = top["category"], int(top["previous_sen"])
    has_budget = any(b["category"].casefold() == category.casefold() for b in inputs.budgets)
    action = (
        Action("link", "Review budgets", href="/budgets")
        if has_budget
        else Action(
            "propose",
            f"Set a {category} budget of {format_rm(before)}",
            action_type="set_budget",
            payload={"category": category, "limit_sen": before},
        )
    )
    month = _month_name(inputs.insights["month"])
    return [
        Recommendation(
            rule="spending_up",
            priority=_rule("spending_up"),
            severity="low",
            title=f"{category} spending rose {format_rm(top['change_sen'])}",
            detail=(
                f"In {month} you spent {format_rm(top['spend_sen'])} on {category}, "
                f"against {format_rm(before)} the month before."
            ),
            sources=[
                Source("Month", month, "text", "get_spending_insights"),
                Source("Spent", top["spend_sen"], "sen", "get_spending_insights"),
                Source("Month before", before, "sen", "get_spending_insights"),
                Source("Change", top["change_sen"], "sen", "get_spending_insights"),
            ],
            action=action,
        )
    ]


def _no_budgets(inputs: Inputs) -> list[Recommendation]:
    if inputs.budgets or int(inputs.budget_status.get("month_spend_sen") or 0) <= 0:
        return []
    return [
        Recommendation(
            rule="no_budgets",
            priority=_rule("no_budgets"),
            severity="low",
            title="Set your first budget",
            detail="Suggest a budget splits what is left after bills and instalments.",
            sources=[],
            action=Action("link", "Suggest a budget", href="/budgets"),
        )
    ]


def recommend(inputs: Inputs) -> list[Recommendation]:
    """Every rule in its fixed order; the result is ranked by rule priority."""
    found = (
        _forecast(inputs)
        + _budgets(inputs)
        + _collisions(inputs)
        + _limits(inputs)
        + _increases(inputs)
        + _spending_up(inputs)
        + _no_budgets(inputs)
    )
    return sorted(found, key=lambda r: r.priority)


def alerts(inputs: Inputs) -> list[Recommendation]:
    """What needs attention now: the subset the assistant opens the conversation with."""
    return [r for r in recommend(inputs) if r.is_alert]
