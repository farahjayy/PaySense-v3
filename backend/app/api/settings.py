"""Per-user settings the person can change (WP16): the savings buffer (ADR D-50).

The buffer is what the person could fall back on if a month runs short. Engine 1's running margin
starts from it (dashboard forecast and risk check), and Engine 2 reads it as a feature.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from app.api.deps import WRITE_QUOTA, CurrentUser, DbDep
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.api.types import MAX_SEN
from app.db import user_settings

router = APIRouter(prefix="/settings", tags=["settings"], responses=PROTECTED_RESPONSES)

BufferSen = Annotated[
    StrictInt,
    Field(ge=0, le=MAX_SEN, description="Savings to fall back on, integer sen; 0 means none"),
]


class SettingsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    savings_buffer_sen: BufferSen


class SettingsOut(ApiModel):
    savings_buffer_sen: int
    onboarding_state: Literal["new", "history_imported", "complete"]


def settings_for(db: Any, user_id: str) -> SettingsOut:
    """Shared by the route and the assistant."""
    row = user_settings.get(db, user_id) or user_settings.create_default(db, user_id)
    return SettingsOut(
        savings_buffer_sen=int(row.get("savings_buffer_sen") or 0),
        onboarding_state=row["onboarding_state"],
    )


@router.get("", response_model=SettingsOut)
def get_settings(user: CurrentUser, db: DbDep) -> SettingsOut:
    return settings_for(db, user.id)


@router.put("", response_model=SettingsOut, dependencies=[WRITE_QUOTA])
def put_settings(body: SettingsIn, user: CurrentUser, db: DbDep) -> SettingsOut:
    """Set the savings buffer. The next forecast and risk check start the running margin from it."""
    user_settings.set_savings_buffer(db, user.id, body.savings_buffer_sen)
    return settings_for(db, user.id)
