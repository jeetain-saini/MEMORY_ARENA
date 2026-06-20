"""InMemoryTraceRecorder — a bounded, process-local ring buffer of traces.

The default recorder (Stage 13). Keeps the most recent ``capacity`` traces so the
``GET /observability/traces`` endpoint can surface them for local inspection and
the dashboard pass. Process-local and not durable — it is an observability aid,
not a trace store (persistent storage is explicitly out of scope for Stage 13).

A single instance is shared process-wide via the factory, so writes from the
query path and reads from the API see the same buffer.
"""

from __future__ import annotations

from collections import deque
from uuid import UUID

from app.application.dto.observability_dto import RequestTrace
from app.application.interfaces.trace_recorder import TraceRecorder


class InMemoryTraceRecorder(TraceRecorder):
    def __init__(self, *, capacity: int = 200) -> None:
        self._buffer: deque[RequestTrace] = deque(maxlen=max(1, capacity))

    async def record(self, trace: RequestTrace) -> None:
        self._buffer.append(trace)

    async def recent(
        self, *, limit: int = 50, user_id: UUID | None = None
    ) -> list[RequestTrace]:
        # Newest first.
        traces = reversed(self._buffer)
        if user_id is not None:
            traces = (t for t in traces if t.user_id == user_id)
        out: list[RequestTrace] = []
        for trace in traces:
            out.append(trace)
            if len(out) >= max(0, limit):
                break
        return out
