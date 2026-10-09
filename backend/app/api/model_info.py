"""Which models are serving: the facts the About-the-model page shows."""

from fastapi import APIRouter, Request

from app.api.deps import CurrentUser
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.engines.forecasting.serving import ARTEFACT_VERSION, SERVED_MODEL

router = APIRouter(prefix="/model-info", tags=["model"], responses=PROTECTED_RESPONSES)


class ForecastModelOut(ApiModel):
    model: str
    version: str


class RiskModelOut(ApiModel):
    available: bool
    version: str | None
    family: str | None
    development_profiles: int | None
    lockbox_brier: float | None
    constant_brier: float | None
    feature_schema_hash: str | None


class ModelInfoOut(ApiModel):
    forecast: ForecastModelOut
    risk: RiskModelOut


@router.get("", response_model=ModelInfoOut)
def model_info(request: Request, user: CurrentUser) -> ModelInfoOut:
    predictor = getattr(request.app.state, "predictor", None)
    summary = getattr(predictor, "summary", {}) if predictor is not None else {}
    return ModelInfoOut(
        forecast=ForecastModelOut(model=SERVED_MODEL, version=ARTEFACT_VERSION),
        risk=RiskModelOut(
            available=predictor is not None,
            version=getattr(predictor, "version", None),
            family=summary.get("family"),
            development_profiles=summary.get("development_profiles"),
            lockbox_brier=summary.get("lockbox_brier"),
            constant_brier=summary.get("constant_brier"),
            feature_schema_hash=getattr(predictor, "feature_schema_hash", None),
        ),
    )
