"""Cap request bodies before they are buffered, parsed or authenticated.

FastAPI reads and parses a body before it resolves the login dependency, and Starlette spools
uploaded files to disk without a size limit, so without this one unauthenticated request could
fill memory or disk. Two defences:
  * a declared `Content-Length` over the limit is refused immediately (nothing is read);
  * a body that streams past the limit (chunked, or a lying header) is cut off with a 413 as soon
    as the running total crosses it.
"""

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_LIMIT_BYTES = 2 * 1024 * 1024  # a 5,000-row import confirm is under 2 MiB
PER_PATH_LIMITS = {"/api/import/csv": 6 * 1024 * 1024}  # the 5 MB file cap plus multipart framing

_TOO_LARGE = {"code": "payload_too_large", "message": "That request is too large."}


class BodySizeLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        default_limit: int = DEFAULT_LIMIT_BYTES,
        per_path: dict[str, int] | None = None,
    ) -> None:
        self.app = app
        self.default_limit = default_limit
        self.per_path = per_path if per_path is not None else PER_PATH_LIMITS

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = self.per_path.get(scope["path"], self.default_limit)
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None:
            try:
                size = int(declared)
            except ValueError:
                await self._refuse(
                    scope, receive, send, 400, "bad_request", "Invalid Content-Length."
                )
                return
            if size > limit:
                await self._refuse(scope, receive, send, 413, **_TOO_LARGE)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    # Raised inside the route, so the app's HTTPException handler turns it into
                    # the standard error envelope (with CORS headers).
                    raise StarletteHTTPException(413, detail=_TOO_LARGE)
            return message

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _refuse(
        scope: Scope, receive: Receive, send: Send, status: int, code: str, message: str
    ) -> None:
        response = JSONResponse(
            status_code=status, content={"detail": {"code": code, "message": message}}
        )
        await response(scope, receive, send)
