"""Trace-recorder factory — config-driven selection (Stage 13).

Selection (mirrors the embedding / LLM / compressor factories):

* ``LANGSMITH_ENABLED=true`` -> ``LangSmithTraceRecorder`` (lazy ``langsmith``).
* otherwise ``TRACE_RECORDER``:
    * ``in_memory`` (default) -> ``InMemoryTraceRecorder`` (recent-readable buffer)
    * ``noop``               -> ``NoOpTraceRecorder``

Cached as a process-wide singleton so the in-memory buffer is shared between the
query path (writes) and the traces endpoint (reads). Call
``build_trace_recorder.cache_clear()`` in tests that change configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.trace_recorder import TraceRecorder
from app.core.config import get_settings


@lru_cache(maxsize=1)
def build_trace_recorder() -> TraceRecorder:
    settings = get_settings()
    if settings.langsmith_enabled:
        from app.infrastructure.observability.langsmith_recorder import LangSmithTraceRecorder

        return LangSmithTraceRecorder(
            api_key=settings.langsmith_api_key, project=settings.langsmith_project
        )
    if settings.trace_recorder.lower() == "noop":
        from app.infrastructure.observability.noop_recorder import NoOpTraceRecorder

        return NoOpTraceRecorder()
    from app.infrastructure.observability.in_memory_recorder import InMemoryTraceRecorder

    return InMemoryTraceRecorder(capacity=settings.trace_recorder_capacity)
