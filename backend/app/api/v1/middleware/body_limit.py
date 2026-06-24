"""Request body-size limit — pure ASGI middleware (production hardening).

Starlette imposes no cap on request body size, so without a guard a single client
can POST an arbitrarily large payload and exhaust memory (the body is buffered and
parsed in full). This middleware rejects requests over ``max_bytes`` with
``413 Payload Too Large``.

It is a *pure ASGI* middleware (not ``BaseHTTPMiddleware``) on purpose:
``BaseHTTPMiddleware`` buffers the response, which breaks Server-Sent-Events
streaming (``/query/stream``) with "Unexpected message received: http.request".
Here we never touch ``send`` — only wrap ``receive`` to count incoming body
bytes — so streaming responses are never disturbed.

Detection: the ``Content-Length`` fast path rejects before the app runs (clean,
enveloped 413). For chunked bodies (no Content-Length) the wrapped ``receive``
raises ``HTTPException(413)`` once the cap is crossed; the framework's exception
middleware turns that into a 413 while the body read is bounded at the cap.
"""

from __future__ import annotations

import json

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import _envelope
from app.core.logging import get_request_id

_MESSAGE = "Request body exceeds the maximum allowed size."


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def _send_413(self, send: Send) -> None:
        body = json.dumps(
            _envelope(get_request_id(), "payload_too_large", _MESSAGE)
        ).encode()
        await send({
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({"type": "http.response.body", "body": body})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        # Fast path: a declared Content-Length over the cap is rejected up front
        # (the realistic case — JSON clients and reverse proxies send it).
        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            return await self._send_413(send)

        total = 0

        async def receive_capped() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_bytes:
                    # Chunked overflow: stop buffering and let the exception
                    # middleware render a 413 (response has not started yet).
                    raise StarletteHTTPException(status_code=413, detail=_MESSAGE)
            return message

        await self.app(scope, receive_capped, send)
