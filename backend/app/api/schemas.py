from typing import Literal

from pydantic import BaseModel, Field

Persona = Literal["frequent_bnpl", "budget_conscious", "irregular_income"]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    persona: Persona | None = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (OAuth token type, not a password)
    expires_in: int = Field(description="Seconds until the session expires")
    user: UserOut
