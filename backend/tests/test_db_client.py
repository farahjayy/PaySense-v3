"""The database client's HTTP settings.

Found on the real database: with supabase-py's default client (HTTP/2 multiplexed over one shared
connection) about one concurrent request in five failed with `httpx.RemoteProtocolError`, which the
app turned into 503 "database not reachable". The dashboard sends about six requests at once, so
every page load was at risk. HTTP/1.1 with a connection pool does not share one stream state
across the threadpool's workers.
"""

import httpx
import pytest

from app.core.settings import Settings
from app.db import client as db_client


@pytest.fixture
def settings() -> Settings:
    return Settings(
        supabase_url="https://example.supabase.co",
        supabase_service_key="service-key-for-tests-only",
        session_secret="x" * 48,
        cors_origins="http://localhost:3000",
        _env_file=None,
    )


def test_the_database_client_does_not_use_http2(settings, monkeypatch):
    captured = {}

    def fake_create_client(url, key, options):
        captured["options"] = options
        return object()

    monkeypatch.setattr(db_client, "create_client", fake_create_client)
    db_client.build_client(settings)

    http = captured["options"].httpx_client
    assert isinstance(http, httpx.Client)
    assert http._transport._pool._http2 is False  # the connection pool is not offering h2
    assert http.timeout.read == db_client.POSTGREST_TIMEOUT_SECONDS
    assert http.follow_redirects is True


def test_a_pool_is_sized_for_the_threadpool_that_uses_it(settings, monkeypatch):
    captured = {}
    monkeypatch.setattr(
        db_client, "create_client", lambda url, key, options: captured.update(o=options)
    )
    db_client.build_client(settings)

    pool = captured["o"].httpx_client._transport._pool
    assert pool._max_connections >= 40  # the server's worker threads, so none waits for a socket
