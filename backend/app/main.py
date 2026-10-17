"""FastAPI app factory.

`create_app(settings)` is what tests use. The module-level `app` that uvicorn imports is built
lazily (and once) so that importing this module never requires a configured environment.
"""

import logging
import sys
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from postgrest import APIError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api import (
    account,
    assistant,
    auth,
    bills,
    budgets,
    categories,
    forecast,
    health,
    imports,
    insights,
    model_info,
    plans,
    provider_limits,
    providers,
    recommendations,
    recurring,
    risk,
    summary,
    transactions,
)
from app.api import settings as settings_api  # `settings` is create_app's parameter name
from app.api.rate_limit import DailyQuota, LoginRateLimiter, RequestRateLimiter
from app.core.body_limit import BodySizeLimitMiddleware
from app.core.settings import MissingSettingsError, Settings, get_settings
from app.db.client import Database
from app.db.transactions import LedgerFullError
from app.engines.risk.artefact import ArtefactError, load_if_present
from app.engines.risk.check import Predictor

_STATUS_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "too_many_requests",
    501: "not_implemented",
}
_STATUS_MESSAGES = {
    404: "Not found.",
    405: "Method not allowed.",
    413: "That request is too large.",
}
_STATUS_CODES[413] = "payload_too_large"

logger = logging.getLogger("paysense")

# Postgres error classes a user's input can legitimately trigger. Anything else is our bug: a 500.
_CONFLICT_CODES = frozenset({"23505", "23503"})  # unique / foreign-key violation
_INVALID_VALUE_CODES = frozenset({"22P05", "22021", "22001", "22003", "22007", "22008", "23514"})


def _envelope(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": {"code": code, "message": message}},
        headers=headers,
    )


def _validation_message(err: RequestValidationError) -> str:
    errors = err.errors()
    if any(e["type"] == "json_invalid" for e in errors):
        return "Request body is not valid JSON."
    parts = []
    for e in errors:
        field = ".".join(str(p) for p in e["loc"] if p != "body")
        parts.append(f"{field}: {e['msg']}" if field else e["msg"])
    return "; ".join(parts)


def _operation_id(route: APIRoute) -> str:
    return route.name  # keeps generated TypeScript names short: `login`, not `login_api_auth_...`


def create_app(
    settings: Settings,
    db: Database | None = None,
    login_limiter: LoginRateLimiter | None = None,
    predictor: Predictor | None = None,
    username_limiter: LoginRateLimiter | None = None,
) -> FastAPI:
    app = FastAPI(title="PaySense API", version="0.1.0", generate_unique_id_function=_operation_id)
    app.state.settings = settings
    app.state.db = db  # built lazily on first use when None (see api/deps.py)
    app.state.login_limiter = login_limiter or LoginRateLimiter()
    # failures against one username from one address (D-49, ASSUMED 31): a stranger elsewhere
    # cannot lock the owner out; spread-out guessing meets the passphrase's own strength
    app.state.username_limiter = username_limiter or LoginRateLimiter(
        max_failures=20, window_seconds=900
    )
    app.state.request_limiter = RequestRateLimiter()
    app.state.write_quota = DailyQuota()
    app.state.predictor = predictor  # the trained risk model; None until an artefact is loaded

    # Added first, so it sits *inside* CORS: its 413 responses still carry CORS headers.
    app.add_middleware(BodySizeLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )

    @app.exception_handler(StarletteHTTPException)
    async def _http_handler(_: Request, err: StarletteHTTPException) -> JSONResponse:
        detail = err.detail
        if isinstance(detail, dict) and {"code", "message"} <= detail.keys():
            code, message = detail["code"], detail["message"]
        else:
            code = _STATUS_CODES.get(err.status_code, f"http_{err.status_code}")
            message = _STATUS_MESSAGES.get(err.status_code) or (
                detail if isinstance(detail, str) else "Request failed."
            )
        return _envelope(err.status_code, code, message, headers=err.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, err: RequestValidationError) -> JSONResponse:
        return _envelope(422, "validation_error", _validation_message(err))

    @app.exception_handler(APIError)
    async def _database_handler(_: Request, err: APIError) -> JSONResponse:
        # Never echo the database's own message: it can name tables, columns and values.
        if err.code in _CONFLICT_CODES:
            return _envelope(409, "conflict", "That conflicts with data that already exists.")
        if err.code in _INVALID_VALUE_CODES:
            return _envelope(422, "invalid_value", "One of the values could not be stored.")
        logger.error("Unexpected database error %s: %s", err.code, err.message)
        return _envelope(500, "internal_error", "Something went wrong on our side.")

    @app.exception_handler(LedgerFullError)
    async def _ledger_full_handler(_: Request, __: LedgerFullError) -> JSONResponse:
        return _envelope(
            413,
            "ledger_full",
            "Your ledger is full. Delete old transactions before adding more.",
        )

    @app.exception_handler(httpx.HTTPError)
    async def _upstream_handler(_: Request, __: httpx.HTTPError) -> JSONResponse:
        return _envelope(
            503, "upstream_unavailable", "The database is not reachable. Try again shortly."
        )

    @app.exception_handler(Exception)
    async def _unexpected_handler(request: Request, __: Exception) -> JSONResponse:
        # Runs in ServerErrorMiddleware, outside CORSMiddleware, so add the CORS header here;
        # otherwise the browser reports an opaque CORS failure instead of our 500.
        response = _envelope(500, "internal_error", "Something went wrong on our side.")
        origin = request.headers.get("origin")
        if origin and origin in settings.cors_origin_list:
            response.headers["access-control-allow-origin"] = origin
            response.headers["vary"] = "Origin"
        return response

    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(providers.router, prefix="/api")
    app.include_router(provider_limits.router, prefix="/api")
    app.include_router(transactions.router, prefix="/api")
    app.include_router(categories.router, prefix="/api")
    app.include_router(summary.router, prefix="/api")
    app.include_router(recurring.router, prefix="/api")
    app.include_router(imports.router, prefix="/api")
    app.include_router(plans.router, prefix="/api")
    app.include_router(bills.router, prefix="/api")
    app.include_router(forecast.router, prefix="/api")
    app.include_router(risk.router, prefix="/api")
    app.include_router(model_info.router, prefix="/api")
    app.include_router(budgets.router, prefix="/api")
    app.include_router(insights.router, prefix="/api")
    app.include_router(recommendations.router, prefix="/api")
    app.include_router(assistant.router, prefix="/api")
    app.include_router(account.router, prefix="/api")
    app.include_router(settings_api.router, prefix="/api")
    return app


_app: FastAPI | None = None


def __getattr__(name: str) -> Any:
    global _app
    if name != "app":
        raise AttributeError(name)
    if _app is None:
        try:
            # A risk model that is present but does not match this code stops start-up here.
            _app = create_app(get_settings(), predictor=load_if_present())
        except MissingSettingsError as err:
            print(err, file=sys.stderr)
            raise SystemExit(2) from err
        except ArtefactError as err:
            print(f"The risk model cannot be served: {err}", file=sys.stderr)
            raise SystemExit(2) from err
    return _app
