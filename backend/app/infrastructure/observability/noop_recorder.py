"""NoOpTraceRecorder — discards traces.

For deployments that want zero observability overhead. ``recent`` always returns
an empty list.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dto.observability_dto import RequestTrace
from app.application.interfaces.trace_recorder import TraceRecorder


class NoOpTraceRecorder(TraceRecorder):
    async def record(self, trace: RequestTrace) -> None:
        return None

    async def recent(
        self, *, limit: int = 50, user_id: UUID | None = None
    ) -> list[RequestTrace]:
        return []
