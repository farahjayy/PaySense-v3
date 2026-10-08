"""Environment-driven settings. A missing required variable fails at startup, by name."""

from functools import lru_cache

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_GUIDE = "refdocs/guides/env_setup.md"
MIN_SECRET_LENGTH = 32


class MissingSettingsError(RuntimeError):
    """Raised when required environment variables are missing or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str = Field(min_length=1)
    supabase_service_key: SecretStr = Field(min_length=1)
    session_secret: SecretStr = Field(min_length=MIN_SECRET_LENGTH)
    cors_origins: str = Field(min_length=1)
    session_ttl_hours: int = Field(default=12, gt=0)

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


def load_settings(env_file: str | None = ".env") -> Settings:
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
