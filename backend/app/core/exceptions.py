"""Application exceptions and global exception handlers.

`AppException` is the base for any error the application raises deliberately; it
carries an HTTP status, a stable machine code, and a safe message. The handlers
translate exceptions — ours, FastAPI validation errors, and anything
unexpected — into the standardized `ErrorResponse` envelope, stamped with the
request's correlation id. Unexpected errors never leak internals to the client.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_request_id
from app.schemas.responses import ErrorDetail, ErrorResponse

_logger = logging.getLogger("memoryarena.error")


class AppException(Exception):
    """Base class for deliberate, expected application errors."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: Any | None = None,
        error_code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details
        if error_code is not None:
            self.error_code = error_code
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.message)


class ServiceUnavailableError(AppException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "service_unavailable"
    message = "A required downstream service is unavailable."


def _envelope(request_id: str, code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    return ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details),
        request_id=request_id,
    ).model_dump()


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the global exception handlers to the FastAPI app."""

    @app.exception_handler(AppException)
    async def _handle_app_exception(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(get_request_id(), exc.error_code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_envelope(
                get_request_id(),
                "validation_error",
                "Request validation failed.",
                details=exc.errors(),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(get_request_id(), "http_error", str(exc.detail)),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Log the full detail server-side; return a generic message to the client.
        _logger.exception("unhandled.exception", extra={"error_type": type(exc).__name__})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_envelope(get_request_id(), "internal_error", "An unexpected error occurred."),
        )
