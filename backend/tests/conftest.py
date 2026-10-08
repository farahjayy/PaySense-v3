import pytest
from fastapi.testclient import TestClient

from app.core.settings import Settings
from app.main import create_app

TEST_SECRET = "test-secret-" + "x" * 40


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
