"""Request body-size limit middleware (production hardening).

Starlette imposes no cap on request body size, so without a guard a single client
can POST an arbitrarily large payload and exhaust memory (the JSON is buffered and
parsed in full). This middleware rejects any request whose ``Content-Length``
exceeds ``max_bytes`` with ``413 Payload Too Large`` in the standard error
envelope, before the body is read. Per-field validation (content/metadata length,
search ``limit``) still applies on top of this whole-request cap.

A reverse proxy (nginx ``client_max_body_size``) should enforce the same limit at
the edge in production; this is the in-app defense in depth, and it covers chunked
requests that omit ``Content-Length`` by streaming-counting the body.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.exceptions import _envelope
from app.core.logging import get_request_id

_MESSAGE = "Request body exceeds the maximum allowed size."


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, max_bytes: int) -> None:
        super().__init__(app)
        self._max_bytes = max_bytes

    def _too_large(self) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content=_envelope(get_request_id(), "payload_too_large", _MESSAGE),
        )

    async def dispatch(self, request: Request, call_next) -> Response:
        # Fast path: trust a declared Content-Length and reject before reading.
        declared = request.headers.get("content-length")
        if declared is not None:
            try:
                if int(declared) > self._max_bytes:
                    return self._too_large()
            except ValueError:
                pass  # malformed header -> fall through to the streaming guard

        # Streaming guard for chunked bodies (no/again Content-Length): count bytes
        # as they arrive and abort once the cap is crossed. We buffer and re-emit
        # the body via a patched receive so the downstream handler still sees it.
        body = b""
        more_body = True
        while more_body:
            message = await request.receive()
            if message["type"] != "http.request":
                continue
            body += message.get("body", b"")
            if len(body) > self._max_bytes:
                return self._too_large()
            more_body = message.get("more_body", False)

        async def _replay() -> dict:
            nonlocal body
            chunk, body = body, b""
            return {"type": "http.request", "body": chunk, "more_body": False}

        request._receive = _replay  # type: ignore[attr-defined]
        return await call_next(request)
