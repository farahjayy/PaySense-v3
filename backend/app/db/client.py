"""Supabase client construction. The backend is the only process that talks to the database."""

from typing import Any, Protocol

import httpx
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from app.core.settings import Settings

# A hung PostgREST call must not hold one of the ~40 threadpool workers for minutes.
POSTGREST_TIMEOUT_SECONDS = 10
# One socket for each worker thread of the server (~40), with a few spare.
POOL_MAX_CONNECTIONS = 48
POOL_KEEPALIVE_CONNECTIONS = 24


class Database(Protocol):
    """The slice of the supabase-py client the repositories rely on (also met by the test fake)."""

    def table(self, name: str) -> Any: ...


def _http_client() -> httpx.Client:
    """HTTP/1.1 with a connection pool. supabase-py's own client speaks HTTP/2 over one shared
    connection, and used from the threadpool concurrently it failed about one request in five
    with `RemoteProtocolError` on the real database; a pool gives each request its own socket."""
    return httpx.Client(
        http2=False,
        timeout=httpx.Timeout(POSTGREST_TIMEOUT_SECONDS),
        follow_redirects=True,
        limits=httpx.Limits(
            max_connections=POOL_MAX_CONNECTIONS,
            max_keepalive_connections=POOL_KEEPALIVE_CONNECTIONS,
        ),
    )


def build_client(settings: Settings) -> Client:
    return create_client(
        settings.supabase_url,
        settings.supabase_service_key.get_secret_value(),
        SyncClientOptions(httpx_client=_http_client()),
    )
