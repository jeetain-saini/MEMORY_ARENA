"""Unit tests for QueryMemoryUseCaseImpl (delegation to the runtime)."""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.application.dto.agent_dto import (
    AgentRequest,
    AgentResponse,
    AgentStreamEvent,
    AgentTrace,
)
from app.application.interfaces.agent_runtime import AgentRuntime
from app.application.use_cases.query_memory_use_cases_impl import QueryMemoryUseCaseImpl


class _SpyRuntime(AgentRuntime):
    def __init__(self) -> None:
        self.responded = None
        self.streamed = None

    async def respond(self, request: AgentRequest) -> AgentResponse:
        self.responded = request
        return AgentResponse(
            query=request.query, user_id=request.user_id, answer="ok",
            citations=[], trace=AgentTrace(), finish_reason="completed",
        )

    async def stream(self, request: AgentRequest):
        self.streamed = request
        yield AgentStreamEvent(event="done", data={"finish_reason": "completed"})


def _req() -> AgentRequest:
    return AgentRequest(user_id=uuid4(), query="hello")


def test_execute_delegates_to_runtime_respond() -> None:
    runtime = _SpyRuntime()
    use_case = QueryMemoryUseCaseImpl(runtime)
    req = _req()
    resp = asyncio.run(use_case.execute(req))
    assert runtime.responded is req
    assert resp.answer == "ok"


def test_execute_returns_agent_response() -> None:
    use_case = QueryMemoryUseCaseImpl(_SpyRuntime())
    resp = asyncio.run(use_case.execute(_req()))
    assert isinstance(resp, AgentResponse)


def test_stream_delegates_to_runtime_stream() -> None:
    runtime = _SpyRuntime()
    use_case = QueryMemoryUseCaseImpl(runtime)
    req = _req()

    async def go() -> list:
        return [ev async for ev in use_case.stream(req)]

    events = asyncio.run(go())
    assert runtime.streamed is req
    assert events[-1].event == "done"


def test_stream_returns_async_iterator() -> None:
    use_case = QueryMemoryUseCaseImpl(_SpyRuntime())
    gen = use_case.stream(_req())
    assert hasattr(gen, "__aiter__")
