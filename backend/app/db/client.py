"""Supabase client construction. The backend is the only process that talks to the database."""

from typing import Any, Protocol

from supabase import Client, create_client

from app.core.settings import Settings


class Database(Protocol):
    """The slice of the supabase-py client the repositories rely on (also met by the test fake)."""

    def table(self, name: str) -> Any: ...


def build_client(settings: Settings) -> Client:
    return create_client(settings.supabase_url, settings.supabase_service_key)
