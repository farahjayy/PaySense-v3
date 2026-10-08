import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.settings import MissingSettingsError, Settings, load_settings

BACKEND_DIR = Path(__file__).resolve().parent.parent
REQUIRED = ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "SESSION_SECRET", "CORS_ORIGINS")


def _clean_env(monkeypatch):
    for name in (*REQUIRED, "SESSION_TTL_HOURS"):
        monkeypatch.delenv(name, raising=False)


def test_cors_origins_are_split_and_stripped():
    s = Settings(
        _env_file=None,
        supabase_url="https://x.supabase.co",
        supabase_service_key="k",
        session_secret="s" * 32,
        cors_origins="http://localhost:3000, https://app.vercel.app ",
    )

    assert s.cors_origin_list == ["http://localhost:3000", "https://app.vercel.app"]


def test_session_ttl_defaults_to_12_hours():
    s = Settings(
        _env_file=None,
        supabase_url="https://x.supabase.co",
        supabase_service_key="k",
        session_secret="s" * 32,
        cors_origins="http://localhost:3000",
    )

    assert s.session_ttl_hours == 12


def test_short_session_secret_is_rejected():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            supabase_url="https://x.supabase.co",
            supabase_service_key="k",
            session_secret="short",
            cors_origins="http://localhost:3000",
        )


def test_load_settings_names_every_missing_variable(monkeypatch):
    _clean_env(monkeypatch)

    with pytest.raises(MissingSettingsError) as exc:
        load_settings(env_file=None)

    message = str(exc.value)
    for name in REQUIRED:
        assert name in message
    assert "env_setup.md" in message


def test_server_exits_naming_session_secret_when_it_is_missing(tmp_path):
    env = {k: v for k, v in os.environ.items() if k not in REQUIRED}
    env.update(
        SUPABASE_URL="https://x.supabase.co",
        SUPABASE_SERVICE_KEY="k",
        CORS_ORIGINS="http://localhost:3000",
        PYTHONPATH=str(BACKEND_DIR),
    )

    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", "import app.main as m; m.app"],
        cwd=tmp_path,  # no .env here, so only the process environment counts
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode != 0
    assert "SESSION_SECRET" in result.stderr
