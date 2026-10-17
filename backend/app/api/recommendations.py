"""Ranked recommendations and proactive alerts (WP15).

A fixed, ordered rule set over engine outputs and the user's own figures. Every recommendation
carries the figures it was made from (`sources`), so nothing on screen is unexplained, and an
action the user can take: a link to a screen, or a pre-filled proposal that still needs their
confirmation (ADR D-48).
"""

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUser, DbDep
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.core.errors import api_error

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


def _not_built():
    return api_error(501, "not_implemented", "This is not available yet.")


@router.get("/recommendations", response_model=RecommendationListOut)
def recommendations(user: CurrentUser, db: DbDep) -> RecommendationListOut:
    raise _not_built()


@router.get("/alerts", response_model=RecommendationListOut)
def alerts(user: CurrentUser, db: DbDep) -> RecommendationListOut:
    raise _not_built()
