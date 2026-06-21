"""Structured (JSON) logging and request-scoped correlation IDs.

Every log line is emitted as a single JSON object so log aggregators (Loki,
ELK, Datadog) can index fields without regex parsing. A per-request correlation
ID is propagated via a `ContextVar`, so any log emitted while handling a request
is automatically stamped with that ID — no need to thread it through call sites.

`RequestContextLogMiddleware` assigns the ID, logs request start/finish with
timing, and echoes the ID back in the `X-Request-ID` response header.
"""

from __future__ import annotations

import json
import logging
import re
import sys
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# Request-scoped correlation id. Default marks logs emitted outside any request.
_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

REQUEST_ID_HEADER = "X-Request-ID"

# --- Log redaction ---------------------------------------------------------
# Sensitive substrings: any structured field whose key contains one of these
# (case-insensitive) has its value replaced before the line is emitted, so
# secrets/credentials never reach the log aggregator. Idempotent — re-redacting
# an already-redacted value leaves it unchanged.
_REDACTED = "***REDACTED***"
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "password", "passwd", "secret", "client_secret", "token", "access_token",
        "refresh_token", "authorization", "api_key", "apikey", "x-api-key",
        "private_key", "jwt", "bearer", "cookie", "set-cookie", "session", "session_id",
    }
)
# Scrub a bearer token embedded in a free-text message; idempotent because the
# redaction placeholder contains no whitespace, so re-matching replaces it with
# itself.
_BEARER_RE = re.compile(r"(?i)(bearer\s+)\S+")


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in _SENSITIVE_KEYS)


def _redact(value: Any) -> Any:
    """Recursively redact sensitive entries in dicts/lists; pass others through."""
    if isinstance(value, dict):
        return {
            key: (_REDACTED if _is_sensitive_key(str(key)) else _redact(val))
            for key, val in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    return value


def _redact_message(message: str) -> str:
    return _BEARER_RE.sub(rf"\g<1>{_REDACTED}", message)

# Standard LogRecord attributes we do NOT want to duplicate into the JSON "extra".
_RESERVED_ATTRS = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info",
    "thread", "threadName", "taskName",
}


def get_request_id() -> str:
    """Return the correlation id bound to the current request (or '-')."""
    return _request_id_ctx.get()


def set_request_id(request_id: str) -> None:
    _request_id_ctx.set(request_id)


class JsonFormatter(logging.Formatter):
    """Render a LogRecord as a one-line JSON document."""

    @staticmethod
    def _timestamp(created: float) -> str:
        # millisecond-precision UTC ISO-8601. (``time.strftime`` does not support
        # ``%f`` portably, so build the timestamp via ``datetime``.)
        dt = datetime.fromtimestamp(created, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self._timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_message(record.getMessage()),
            "request_id": get_request_id(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Merge structured `extra={...}` fields the caller attached, redacting any
        # sensitive keys (and recursing into nested dict/list values).
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload.setdefault(
                    key, _REDACTED if _is_sensitive_key(key) else _redact(value)
                )

        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    """Install the JSON formatter on the root logger (idempotent)."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # Hand uvicorn's loggers to our handler so all output is uniform JSON.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True


class RequestContextLogMiddleware(BaseHTTPMiddleware):
    """Assign a correlation id, log the request lifecycle, time the handler."""

    def __init__(self, app: Any) -> None:
        super().__init__(app)
        self._logger = logging.getLogger("memoryarena.request")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        set_request_id(request_id)
        start = time.perf_counter()

        self._logger.info(
            "request.start",
            extra={"method": request.method, "path": request.url.path,
                   "client": request.client.host if request.client else None},
        )

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            self._logger.exception(
                "request.error",
                extra={"method": request.method, "path": request.url.path,
                       "duration_ms": duration_ms},
            )
            raise

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = request_id
        self._logger.info(
            "request.finish",
            extra={"method": request.method, "path": request.url.path,
                   "status_code": response.status_code, "duration_ms": duration_ms},
        )
        return response
