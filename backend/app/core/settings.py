"""Environment-driven settings. A missing required variable fails at startup, by name."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_GUIDE = "docs/env_setup.md"
# One `.env` at the repo root can serve both apps; `backend/.env` (read second) overrides it.
ENV_FILES = (Path(__file__).resolve().parents[3] / ".env", ".env")
MIN_SECRET_LENGTH = 32


class MissingSettingsError(RuntimeError):
    """Raised when required environment variables are missing or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILES, extra="ignore")

    supabase_url: str = Field(min_length=1)
    supabase_service_key: SecretStr = Field(min_length=1)
    session_secret: SecretStr = Field(min_length=MIN_SECRET_LENGTH)
    cors_origins: str = Field(min_length=1)
    session_ttl_hours: int = Field(default=12, gt=0)
    # ASSUMED (D-49): writes one person may make per Malaysian day, across every write route.
    # A busy real user makes tens; an import is one write however many rows it holds.
    daily_write_quota: int = Field(default=300, ge=0)

    # ---- the assistant (ADRs D-47, D-48, D-53). Keys are optional: none means guided mode.
    assistant_enabled: bool = True
    llm_provider: Literal["gemini", "anthropic", "none"] = "gemini"
    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None
    assistant_model: str | None = None  # None: the provider adapter's default model
    # Transaction descriptions are user text (merchant names, notes, injected instructions): kept
    # from the LLM provider unless a deployment turns this off.
    assistant_redact_descriptions: bool = True
    assistant_max_tool_calls: int = Field(default=6, ge=1, le=12)  # ASSUMED 16 (D-47)
    assistant_max_output_tokens: int = Field(default=1024, ge=64, le=8192)
    assistant_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    assistant_history_turns: int = Field(default=8, ge=0, le=12)
    # ASSUMED 29: a turn costs about 6-12k tokens (measured on Gemini), so ~20 turns per user a day
    assistant_user_daily_tokens: int = Field(default=200_000, ge=0)
    assistant_global_daily_tokens: int = Field(default=3_000_000, ge=0)
    # every assistant chat or guided call writes audit rows: a daily cap bounds them (WP8 review)
    assistant_daily_requests: int = Field(default=300, ge=0)
    assistant_action_ttl_minutes: int = Field(default=10, ge=1, le=60)  # ASSUMED 17 (D-48)

    # ---- Sign in with Google (ADR D-69). Off unless the client ID, secret and the API's public
    # URL are all set; the redirect URI is API_PUBLIC_URL + /api/auth/google/callback.
    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    api_public_url: str | None = None  # the origin the browser uses for the API, no trailing slash
    app_url: str | None = None  # the frontend origin; defaults to the first CORS origin

    @field_validator("cors_origins")
    @classmethod
    def _origins_are_explicit(cls, value: str) -> str:
        origins = [o.strip() for o in value.split(",") if o.strip()]
        if not origins:
            raise ValueError("list at least one origin, e.g. http://localhost:3000")
        for origin in origins:
            if origin == "*":
                raise ValueError("a wildcard origin is not allowed; list explicit origins")
            if origin.endswith("/"):
                raise ValueError(f"no trailing slash: {origin}")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def google_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret and self.api_public_url)

    @property
    def frontend_url(self) -> str:
        return (self.app_url or self.cors_origin_list[0]).rstrip("/")


def load_settings(env_file: tuple[Path | str, ...] | str | None = ENV_FILES) -> Settings:
    """Build Settings or raise MissingSettingsError naming every offending variable."""
    try:
        return Settings(_env_file=env_file)
    except ValidationError as err:
        problems = [f"{str(e['loc'][0]).upper()}: {e['msg']}" for e in err.errors()]
        raise MissingSettingsError(
            "Invalid or missing environment configuration:\n  "
            + "\n  ".join(problems)
            + f"\nSee {ENV_GUIDE} for where to get each value."
        ) from err


@lru_cache
def get_settings() -> Settings:
    return load_settings()
