"""Ranked recommendations and proactive alerts (WP15).

A fixed, ordered rule set over engine outputs and the user's own figures. Every recommendation
carries the figures it was made from (`sources`), so nothing on screen is unexplained, and an
action the user can take: a link to a screen, or a pre-filled proposal that still needs their
confirmation (ADR D-48).
"""

import datetime as dt
from dataclasses import asdict
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import Field

from app.api import budgets as budgets_api
from app.api.deps import CurrentUser, DbDep, TodayDep, rate_limited
from app.api.forecast import ForecasterDep, forecast_for
from app.api.insights import bills_for, spending_for
from app.api.provider_limits import limits_for
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.domain import recommendations as rules

router = APIRouter(tags=["recommendations"], responses=PROTECTED_RESPONSES)

Unit = Literal["sen", "percent", "probability", "count", "date", "text"]
Severity = Literal["high", "medium", "low"]


class SourceFigureOut(ApiModel):
    label: str
    value: int | float | str
    unit: Unit
    source: str = Field(description="The tool or endpoint the figure came from")


class SuggestedActionOut(ApiModel):
    kind: Literal["link", "propose"]
    label: str
    href: str | None = None
    action_type: Literal["set_budget"] | None = None
    payload: dict[str, str | int] | None = None


class RecommendationOut(ApiModel):
    is_alert: bool = Field(description="Needs attention now; the assistant opens with these")
    rule: str = Field(description="Stable rule key, e.g. 'forecast_shortfall'")
    priority: int = Field(description="Lower comes first; fixed per rule")
    severity: Severity
    title: str
    detail: str
    sources: list[SourceFigureOut]
    action: SuggestedActionOut | None


class RecommendationListOut(ApiModel):
    items: list[RecommendationOut]
    checked_rules: list[str] = Field(description="Every rule evaluated, fired or not")
    notes: list[str]


def _last_complete_month(today: dt.date) -> str:
    first = today.replace(day=1)
    return (first - dt.timedelta(days=1)).strftime("%Y-%m")


def inputs_for(db: Any, user_id: str, today: dt.date, forecaster: Any) -> rules.Inputs:
    """Every figure the rules read, from the same shared functions the screens use."""
    budgets = budgets_api.list_for(db, user_id).budgets
    return rules.Inputs(
        today=today,
        forecast=forecast_for(db, user_id, today, forecaster).model_dump(mode="json"),
        budget_status=budgets_api.status_for(
            db, user_id, today.strftime("%Y-%m"), today
        ).model_dump(mode="json"),
        budgets=[b.model_dump(mode="json") for b in budgets],
        bills=bills_for(db, user_id, today).model_dump(mode="json"),
        insights=spending_for(db, user_id, _last_complete_month(today)).model_dump(mode="json"),
        limits=[row.model_dump(mode="json") for row in limits_for(db, user_id)],
    )


def recommendations_for(
    db: Any, user_id: str, today: dt.date, forecaster: Any, *, alerts_only: bool = False
) -> RecommendationListOut:
    """Shared by both routes and the assistant's `get_recommendations` / `get_alerts` tools."""
    inputs = inputs_for(db, user_id, today, forecaster)
    found = rules.alerts(inputs) if alerts_only else rules.recommend(inputs)
    return RecommendationListOut(
        items=[RecommendationOut.model_validate(asdict(r)) for r in found],
        checked_rules=list(rules.RULES),
        notes=inputs.notes,
    )


# Both run Engine 1's forecast, so they share its per-user limit.
FORECAST_LIMIT = rate_limited("forecast", 30, 60)


@router.get("/recommendations", response_model=RecommendationListOut, dependencies=[FORECAST_LIMIT])
def recommendations(
    user: CurrentUser, db: DbDep, today: TodayDep, forecaster: ForecasterDep
) -> RecommendationListOut:
    """Ranked by a fixed rule order; each carries the figures it was made from."""
    return recommendations_for(db, user.id, today, forecaster)


@router.get("/alerts", response_model=RecommendationListOut, dependencies=[FORECAST_LIMIT])
def alerts(
    user: CurrentUser, db: DbDep, today: TodayDep, forecaster: ForecasterDep
) -> RecommendationListOut:
    """Only what needs attention now: a budget over its limit, payments colliding within a
    week, an At Risk forecast."""
    return recommendations_for(db, user.id, today, forecaster, alerts_only=True)
