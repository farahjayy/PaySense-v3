"""The security drill (ADR D-58): the four named attack classes, run on request against a
throwaway sandbox. Stateless for the caller: their own data is never read or written."""

import time
from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import CurrentUser, SettingsDep, rate_limited
from app.api.schemas import PROTECTED_RESPONSES, ApiModel
from app.security import drill

router = APIRouter(prefix="/security", tags=["security"], responses=PROTECTED_RESPONSES)

AttackClass = Literal["induced_transfers", "data_extraction", "privilege_escalation",
                      "prompt_injection"]  # fmt: skip
DRILLS_PER_MINUTE = 2


class DrillAttackOut(ApiModel):
    id: str
    attack_class: AttackClass
    title: str
    tried: str = Field(description="What the hostile model (or attacker) did")
    stopped_by: str = Field(description="The control meant to stop it")
    fooled: bool = Field(description="The model really issued the malicious call")
    harmed: bool = Field(description="Measured on the sandbox after the attack")
    evidence: str


class DrillClassOut(ApiModel):
    attack_class: AttackClass
    attacks: int
    fooled: int
    harmed: int


class DrillOut(ApiModel):
    attacks: list[DrillAttackOut]
    totals: list[DrillClassOut]
    duration_ms: int
    sandbox: Literal[True] = True
    model: Literal["scripted_hostile"] = Field(
        default="scripted_hostile",
        description="A scripted model that obeys every injected instruction (the worst case)",
    )


@router.post(
    "/drill",
    response_model=DrillOut,
    dependencies=[rate_limited("security-drill", DRILLS_PER_MINUTE, 60)],
)
def run_drill(user: CurrentUser, settings: SettingsDep) -> DrillOut:
    """Run every attack against its own sandbox and report what the model was made to try and
    what harm was done. Nothing about the signed-in user is read or written."""
    start = time.perf_counter()
    result = drill.run(settings)
    return DrillOut(
        attacks=[DrillAttackOut(**a.__dict__) for a in result.attacks],
        totals=[DrillClassOut(**t.__dict__) for t in result.totals],
        duration_ms=round((time.perf_counter() - start) * 1000),
    )
