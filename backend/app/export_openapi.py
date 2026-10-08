"""Write the OpenAPI document to a file, with no database, credentials or running server.

    cd backend && uv run python -m app.export_openapi ../frontend/openapi.json

`npm run gen:api` (frontend) calls this, then runs openapi-typescript on the result (ADR D-18).
The settings are placeholders: building the app and its schema never touches them.
"""

import json
import sys
from pathlib import Path
from typing import Any

from app.core.settings import Settings
from app.main import create_app

DEFAULT_TARGET = Path("openapi.json")


def build_openapi() -> dict[str, Any]:
    placeholder = Settings(
        _env_file=None,
        supabase_url="https://placeholder.invalid",
        supabase_service_key="placeholder",
        session_secret="x" * 32,
        cors_origins="http://localhost:3000",
    )
    return create_app(placeholder).openapi()


def write_openapi(target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(build_openapi(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_openapi(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET)
