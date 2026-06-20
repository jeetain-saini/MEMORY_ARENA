"""TraceRecorder port — a sink for request-scoped observability traces.

The query pipeline produces a ``RequestTrace`` per run (Stage 13 Phase A); this
port lets the application *record* those traces without knowing where they go.
Adapters: a no-op, an in-memory ring buffer (the default — recent traces are
readable via the API), and an optional LangSmith exporter (feature-flagged, lazy
import, disabled by default).

``record`` is best-effort and must never break the request. ``recent`` is a
read-back for local inspection; exporters that ship traces elsewhere (LangSmith)
return an empty list.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from app.application.dto.observability_dto import RequestTrace


class TraceRecorder(ABC):
    @abstractmethod
    async def record(self, trace: RequestTrace) -> None:
        """Record one request trace. Best-effort; never raises to the caller."""

    @abstractmethod
    async def recent(
        self, *, limit: int = 50, user_id: UUID | None = None
    ) -> list[RequestTrace]:
        """Return the most recent traces (newest first), optionally per-tenant."""
