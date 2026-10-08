"""Per-provider limits (ADR D-28). A limit caps how much of a purchase the provider can finance."""

from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel

from app.api.deps import CurrentUser, DbDep
from app.api.schemas import NOT_FOUND_RESPONSE, PROTECTED_RESPONSES, ApiModel
from app.api.types import Sen
from app.core.errors import not_found
from app.db import plans as plans_repo
from app.db import provider_limits as limits_repo
from app.domain.plans import remaining_limit_sen

# The manual "Other provider" path takes no limit: the user types what their checkout shows.
NamedProvider = Literal["spaylater", "tiktok_paylater", "atome"]
NAMED_PROVIDERS: tuple[NamedProvider, ...] = ("spaylater", "tiktok_paylater", "atome")

router = APIRouter(
    prefix="/provider-limits", tags=["provider-limits"], responses=PROTECTED_RESPONSES
)


class LimitIn(BaseModel):
    limit_sen: Sen


class LimitOut(ApiModel):
    provider: NamedProvider
    limit_sen: int | None
    used_sen: int
    remaining_sen: int | None


def _out(provider: NamedProvider, limit_sen: int | None, used_sen: int) -> LimitOut:
    return LimitOut(
        provider=provider,
        limit_sen=limit_sen,
        used_sen=used_sen,
        remaining_sen=remaining_limit_sen(limit_sen, used_sen),
    )


@router.get("", response_model=list[LimitOut])
def list_limits(user: CurrentUser, db: DbDep) -> list[LimitOut]:
    stored = {row["provider"]: row["limit_sen"] for row in limits_repo.list_limits(db, user.id)}
    used = plans_repo.used_limits(db, user.id)
    return [_out(p, stored.get(p), used.get(p, 0)) for p in NAMED_PROVIDERS]


@router.put("/{provider}", response_model=LimitOut)
def put_limit(provider: NamedProvider, body: LimitIn, user: CurrentUser, db: DbDep) -> LimitOut:
    row = limits_repo.upsert_limit(db, user.id, provider, body.limit_sen)
    return _out(provider, row["limit_sen"], plans_repo.used_limits(db, user.id).get(provider, 0))


@router.delete("/{provider}", status_code=204, responses=NOT_FOUND_RESPONSE)
def delete_limit(provider: NamedProvider, user: CurrentUser, db: DbDep) -> Response:
    if not limits_repo.delete_limit(db, user.id, provider):
        raise not_found("limit_not_found", "No limit is recorded for that provider.")
    return Response(status_code=204)
