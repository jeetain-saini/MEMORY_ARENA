"""Phase 3: backend runtime hardening.

* Fire-and-forget conversation-capture tasks are tracked (no orphan / GC-pending
  task) and self-remove on completion.
* The SSE event source deterministically finalizes the underlying agent stream
  (aclose) on completion and on client disconnect — no suspended generator / DB
  session left open.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.api.v1.routes.query import query_stream
from app.application.dto.agent_dto import AgentConfig, AgentStreamEvent
from app.application.services.agent import conversation_capture_service as cap_mod
from app.application.services.agent.conversation_capture_policy import (
    ConversationCapturePolicy,
)
from app.application.services.agent.conversation_capture_service import (
    ConversationCaptureService,
)
from app.schemas.query import QueryRequestSchema


def test_schedule_tracks_task_and_drains() -> None:
    async def scenario() -> None:
        submitted = []

        class _FakeProcessor:
            async def submit(self, job) -> None:  # noqa: ANN001
                submitted.append(job)

        svc = ConversationCaptureService(
            _FakeProcessor(), ConversationCapturePolicy(min_tokens=1), enabled=True
        )
        svc.schedule(uuid4(), "i am learning rust and i really prefer typescript")
        assert len(cap_mod._pending_captures) == 1  # reference held -> no orphan
        await asyncio.gather(*list(cap_mod._pending_captures))
        assert len(submitted) == 1                  # work actually ran
        assert len(cap_mod._pending_captures) == 0  # self-removed on completion

    asyncio.run(scenario())


def test_schedule_noop_when_disabled() -> None:
    async def scenario() -> None:
        svc = ConversationCaptureService(
            object(), ConversationCapturePolicy(min_tokens=1), enabled=False
        )
        svc.schedule(uuid4(), "anything")
        assert len(cap_mod._pending_captures) == 0

    asyncio.run(scenario())


class _TrackingStream:
    """Async iterator that records whether it was explicitly closed."""

    def __init__(self) -> None:
        self.closed = False
        self._items = iter([AgentStreamEvent(event="answer", data={"text": "hi"})])

    def __aiter__(self) -> "_TrackingStream":
        return self

    async def __anext__(self) -> AgentStreamEvent:
        try:
            return next(self._items)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def aclose(self) -> None:
        self.closed = True


def test_sse_finalizes_underlying_stream_on_completion() -> None:
    async def scenario() -> None:
        stream = _TrackingStream()

        class _FakeUseCase:
            def stream(self, request):  # noqa: ANN001
                return stream

        payload = QueryRequestSchema(user_id=uuid4(), query="hello")
        resp = await query_stream(payload, _FakeUseCase(), AgentConfig())
        # Drain the SSE body the way the server would.
        async for _ in resp.body_iterator:
            pass
        assert stream.closed is True  # underlying stream finalized -> no leak

    asyncio.run(scenario())


def test_sse_finalizes_underlying_stream_on_disconnect() -> None:
    async def scenario() -> None:
        stream = _TrackingStream()

        class _FakeUseCase:
            def stream(self, request):  # noqa: ANN001
                return stream

        payload = QueryRequestSchema(user_id=uuid4(), query="hello")
        resp = await query_stream(payload, _FakeUseCase(), AgentConfig())
        gen = resp.body_iterator
        await gen.__anext__()          # consume first frame
        await gen.aclose()             # simulate client disconnect mid-stream
        assert stream.closed is True   # finally still finalized the stream

    asyncio.run(scenario())
