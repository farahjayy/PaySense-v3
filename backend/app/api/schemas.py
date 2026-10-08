from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Persona = Literal["frequent_bnpl", "budget_conscious", "irregular_income"]

# Fields with defaults are still always sent; mark them required in the generated OpenAPI so the
# TypeScript types do not make them optional.
_ALWAYS_SENT = ConfigDict(json_schema_serialization_defaults_required=True)


class ErrorDetail(BaseModel):
    code: str = Field(description="Stable machine-readable code")
    message: str = Field(description="Human-readable explanation")


class ErrorEnvelope(BaseModel):
    """Every non-2xx response from this API has this shape."""

    detail: ErrorDetail


ERROR_RESPONSES: dict[int | str, dict] = {
    401: {"model": ErrorEnvelope, "description": "Not logged in, or the session is invalid"},
    422: {"model": ErrorEnvelope, "description": "The request body or parameters are invalid"},
    429: {"model": ErrorEnvelope, "description": "Too many failed attempts"},
}


class HealthOut(BaseModel):
    status: Literal["ok"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class UserOut(BaseModel):
    model_config = _ALWAYS_SENT

    id: str
    username: str
    display_name: str
    persona: Persona | None = None


class LoginResponse(BaseModel):
    model_config = _ALWAYS_SENT

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (OAuth token type, not a password)
    expires_in: int = Field(description="Seconds until the session expires")
    user: UserOut
