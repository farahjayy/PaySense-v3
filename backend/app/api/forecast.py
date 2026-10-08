"""The dashboard forecast: three months of margin, the chance of a shortfall, a health score."""

import datetime as dt
import zlib
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import Field

from app.api.deps import CurrentUser, DbDep, TodayDep
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.db import plans as plans_repo
from app.db import recurring_items, transactions
from app.engines.forecasting.service import build_forecast
from app.engines.forecasting.serving import served_forecaster
from app.engines.forecasting.simulate import Forecaster

router = APIRouter(prefix="/forecast", tags=["forecast"], responses=PROTECTED_RESPONSES)


def get_forecaster() -> Forecaster:
    return served_forecaster()


ForecasterDep = Annotated[Forecaster, Depends(get_forecaster)]


class SuspectMonthOut(ApiModel):
    month: str
    reason: Literal["no_income", "low_spend"]
    detail: str


class SimulationOut(ApiModel):
    months: list[str]
    monthly_margin_p10_sen: list[int]
    monthly_margin_p50_sen: list[int]
    monthly_margin_p90_sen: list[int]
    cumulative_margin_p10_sen: list[int]
    cumulative_margin_p50_sen: list[int]
    cumulative_margin_p90_sen: list[int]
    p_shortfall: float = Field(ge=0, le=1)
    worst_month: str | None
    weeks: int
    horizon_capped: bool
    bootstrap: Literal["block", "plain", "none"]


class ForecastOut(ApiModel):
    status: Literal["ok", "locked"]
    as_of: dt.date
    model: str
    months_of_history: int
    suspect_months: list[SuspectMonthOut]
    lock_reason: Literal["needs_four_months", "no_usable_history"] | None
    simulation: SimulationOut | None
    band: Literal["Safe", "Caution", "At Risk"] | None
    health_score: int | None


def _seed(user_id: str, today: dt.date) -> int:
    """Deterministic per user and day, so reloading the page does not move the numbers."""
    return zlib.crc32(f"{user_id}:{today.isoformat()}".encode())


@router.get("", response_model=ForecastOut)
def forecast(user: CurrentUser, db: DbDep, today: TodayDep, model: ForecasterDep) -> ForecastOut:
    result = build_forecast(
        rows=transactions.list_for_forecast(db, user.id, today),
        items=recurring_items.list_items(db, user.id, active_only=True),
        plans=plans_repo.list_with_instalments(db, user.id),
        today=today,
        forecaster=model,
        seed=_seed(user.id, today),
    )
    simulation = result.simulation
    shown = None
    if simulation is not None:
        shown = {name: getattr(simulation, name) for name in SimulationOut.model_fields}
    payload = {
        "status": result.status,
        "as_of": today,
        "model": model.name,
        "months_of_history": result.months_of_history,
        "suspect_months": [vars(s) for s in result.suspect_months],
        "lock_reason": result.lock_reason,
        "simulation": shown,
        "band": result.band,
        "health_score": result.health_score,
    }
    return ForecastOut.model_validate(payload)
