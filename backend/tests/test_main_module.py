from app import main
from app.core.settings import get_settings


def test_module_level_app_is_built_once(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "k")
    monkeypatch.setenv("SESSION_SECRET", "s" * 40)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    get_settings.cache_clear()
    monkeypatch.setattr(main, "_app", None)

    first = main.__getattr__("app")
    second = main.__getattr__("app")

    assert first is second
    get_settings.cache_clear()
