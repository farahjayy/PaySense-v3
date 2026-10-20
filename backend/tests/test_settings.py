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

    # The settings also read the repo-root .env by absolute path; switch that off so only the
    # process environment counts, as on a server with no .env.
    no_env_file = (
        "import app.core.settings as s; s.Settings.model_config['env_file'] = None; "
        "s.load_settings.__defaults__ = (None,); import app.main as m; m.app"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", no_env_file],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode != 0
    assert "SESSION_SECRET" in result.stderr


def _kwargs(**overrides):
    base = dict(
        _env_file=None,
        supabase_url="https://x.supabase.co",
        supabase_service_key="k",
        session_secret="s" * 32,
        cors_origins="http://localhost:3000",
    )
    return base | overrides


@pytest.mark.parametrize("field", ["supabase_url", "supabase_service_key", "cors_origins"])
def test_empty_values_are_rejected(field):
    with pytest.raises(ValidationError):
        Settings(**_kwargs(**{field: ""}))


@pytest.mark.parametrize("origins", ["*", "http://localhost:3000/", "http://a.com, *", " , "])
def test_unsafe_cors_origins_are_rejected(origins):
    with pytest.raises(ValidationError):
        Settings(**_kwargs(cors_origins=origins))


def test_secrets_do_not_appear_in_repr():
    s = Settings(**_kwargs(session_secret="topsecretvalue" * 3, supabase_service_key="svc-key-123"))

    text = repr(s) + str(s)
    assert "topsecretvalue" not in text
    assert "svc-key-123" not in text
    assert s.session_secret.get_secret_value().startswith("topsecretvalue")


def test_a_root_env_serves_the_backend_and_backend_env_overrides_it(monkeypatch, tmp_path):
    _clean_env(monkeypatch)
    root, local = tmp_path / "root.env", tmp_path / "local.env"
    root.write_text("SUPABASE_URL=https://root.supabase.co\nSUPABASE_SERVICE_KEY=k\n"
                    f"SESSION_SECRET={'s' * 32}\nCORS_ORIGINS=http://localhost:3000\n")  # fmt: skip
    local.write_text("SUPABASE_URL=https://local.supabase.co\n")
    assert load_settings(env_file=(root,)).supabase_url == "https://root.supabase.co"
    assert load_settings(env_file=(root, local)).supabase_url == "https://local.supabase.co"


def test_memory_backend_needs_no_supabase_credentials(monkeypatch):
    """D-71: DB_BACKEND=memory runs locally without Supabase; production keeps requiring it."""
    _clean_env(monkeypatch)
    s = Settings(_env_file=None, db_backend="memory", session_secret="s" * 32,
                 cors_origins="http://localhost:3000")  # fmt: skip
    assert s.supabase_url is None
    with pytest.raises(ValidationError, match="DB_BACKEND=memory"):
        Settings(_env_file=None, session_secret="s" * 32, cors_origins="http://localhost:3000")
