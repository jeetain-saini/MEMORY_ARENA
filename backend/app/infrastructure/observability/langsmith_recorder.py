"""LangSmithTraceRecorder — optional export of request traces to LangSmith.

Feature-flagged (``LANGSMITH_ENABLED``, default off) and **lazily imported**: the
``langsmith`` package is only imported when a real client is constructed, so the
module imports cleanly without the dependency and the offline test suite never
needs it (mirroring the lazy ``langgraph`` runtimes).

Export is best-effort: any failure is logged and swallowed so observability can
never break a query. ``recent`` returns an empty list — traces live in the
LangSmith UI, not here.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from app.application.dto.observability_dto import RequestTrace
from app.application.interfaces.trace_recorder import TraceRecorder

_logger = logging.getLogger("memoryarena.observability.langsmith")


class LangSmithTraceRecorder(TraceRecorder):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        project: str = "memoryarena",
        client: Any | None = None,
    ) -> None:
        if client is None:
            from langsmith import Client  # lazy import — only when actually used

            client = Client(api_key=api_key)
        self._client = client
        self._project = project

    async def record(self, trace: RequestTrace) -> None:
        try:
            self._client.create_run(
                name="memory_query",
                run_type="chain",
                project_name=self._project,
                inputs={"query": trace.query, "user_id": str(trace.user_id)},
                outputs={
                    "finish_reason": trace.finish_reason,
                    "total_duration_ms": trace.total_duration_ms,
                    "tool_calls": trace.tool_calls,
                    "total_tokens": trace.total_tokens,
                },
                extra={"timings": [(t.step, t.duration_ms) for t in trace.timings]},
            )
        except Exception as exc:  # noqa: BLE001 — observability must never break a request
            _logger.warning("langsmith.record_failed", extra={"error": str(exc)})

    async def recent(
        self, *, limit: int = 50, user_id: UUID | None = None
    ) -> list[RequestTrace]:
        return []
