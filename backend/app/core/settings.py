"""Environment-driven settings. A missing required variable fails at startup, by name."""

from functools import lru_cache

from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_GUIDE = "refdocs/guides/env_setup.md"
MIN_SECRET_LENGTH = 32


class MissingSettingsError(RuntimeError):
    """Raised when required environment variables are missing or invalid."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_service_key: str
    session_secret: str = Field(min_length=MIN_SECRET_LENGTH)
    cors_origins: str
    session_ttl_hours: int = Field(default=12, gt=0)

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
