"""Structured HTTP errors: every expected failure carries a machine code and a readable message."""

from fastapi import HTTPException


def api_error(
    status_code: int, code: str, message: str, headers: dict[str, str] | None = None
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
        headers=headers,
    )


def not_found(code: str, message: str) -> HTTPException:
    return api_error(404, code, message)


def bad_request(code: str, message: str) -> HTTPException:
    return api_error(400, code, message)


def unauthorized(code: str, message: str) -> HTTPException:
    return api_error(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def conflict(code: str, message: str) -> HTTPException:
    return api_error(409, code, message)


def unprocessable(code: str, message: str) -> HTTPException:
    return api_error(422, code, message)
