import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

TEST_SECRET = "test-secret-" + "x" * 40
# Settings read the environment as well as their arguments. Tests must never reach a real model
# provider, whatever keys the machine running them holds (ADR D-53: tests use the fake LLM).
LLM_ENVIRONMENT = ("GEMINI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER", "ASSISTANT_MODEL")


@pytest.fixture(autouse=True)
def _no_real_llm_keys(monkeypatch):
    for name in LLM_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        supabase_url="https://example.supabase.co",
        supabase_service_key="service-key-for-tests",
        session_secret=TEST_SECRET,
        cors_origins="http://localhost:3000",
    )


@pytest.fixture
def client(settings: Settings) -> TestClient:
    return TestClient(create_app(settings))
