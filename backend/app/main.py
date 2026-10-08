"""FastAPI app factory.

`create_app(settings)` is what tests use. The module-level `app` that uvicorn imports is built
lazily so that importing this module never requires a configured environment.
"""

import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import health
from app.core.settings import MissingSettingsError, Settings, get_settings


def _envelope(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"detail": {"code": code, "message": message}}
    )


def _validation_message(err: RequestValidationError) -> str:
    parts = []
    for e in err.errors():
        field = ".".join(str(p) for p in e["loc"] if p != "body")
        parts.append(f"{field}: {e['msg']}" if field else e["msg"])
    return "; ".join(parts)


def create_app(settings: Settings) -> FastAPI:
    app = FastAPI(title="PaySense API", version="0.1.0")
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, err: RequestValidationError) -> JSONResponse:
        return _envelope(422, "validation_error", _validation_message(err))

    @app.exception_handler(Exception)
    async def _unexpected_handler(_: Request, __: Exception) -> JSONResponse:
        return _envelope(500, "internal_error", "Something went wrong on our side.")

    app.include_router(health.router, prefix="/api")
    return app


def __getattr__(name: str) -> Any:
    if name != "app":
        raise AttributeError(name)
    try:
        return create_app(get_settings())
    except MissingSettingsError as err:
        print(err, file=sys.stderr)
        raise SystemExit(2) from err
