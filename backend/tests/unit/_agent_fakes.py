"""Shared offline fakes for the query-time agent tests.

Fakes for the three wrapped services plus an LLM provider, so the agent runtime,
tools, and use case can be exercised with no DB, no graph server, and no network.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from app.application.dto.context_dto import (
    CompressionStats,
    ContextMemory,
    ContextPackage,
    ContextRequest,
)
from app.application.dto.graph_dto import ExpandedMemory, GraphAwareResult
from app.application.dto.retrieval_dto import (
    MemorySearchQuery,
    RetrievalResult,
    RetrievedMemory,
    ScoreBreakdown,
)
from app.application.interfaces.llm_provider import LLMProvider
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


def make_retrieved(
    content: str, user_id: UUID, *, score: float = 0.9, memory_type: MemoryType = MemoryType.FACT
) -> RetrievedMemory:
    mid = uuid4()
    return RetrievedMemory(
        memory_id=mid,
        user_id=user_id,
        content=content,
        memory_type=memory_type,
        status=MemoryStatus.ACTIVE,
        final_score=score,
        scores=ScoreBreakdown(0.0, 0.0, 0.0, 0.0, score),
    )


class FakeRetrievalService:
    def __init__(self, results: list[RetrievedMemory] | None = None, *, raises: bool = False) -> None:
        self._results = results or []
        self._raises = raises

    async def search(self, query: MemorySearchQuery) -> RetrievalResult:
        if self._raises:
            raise RuntimeError("retrieval down")
        return RetrievalResult(
            query=query.query, user_id=query.user_id, results=self._results, count=len(self._results)
        )


class FakeGraphAwareService:
    """Expands by appending fixed graph neighbors; reuses base hits as hybrid."""

    def __init__(self, neighbors: list[tuple[str, UUID]] | None = None, *, raises: bool = False) -> None:
        self._neighbors = neighbors or []
        self._raises = raises

    async def expand(self, base: RetrievalResult, query: MemorySearchQuery, *, expand_depth=None) -> GraphAwareResult:
        if self._raises:
            raise RuntimeError("graph down")
        results: list[ExpandedMemory] = []
        for hit in base.results:
            results.append(
                ExpandedMemory(
                    memory_id=hit.memory_id, content=hit.content, memory_type=hit.memory_type,
                    status=hit.status, score=hit.final_score, provenance="hybrid",
                )
            )
        graph_count = 0
        for content, mid in self._neighbors:
            results.append(
                ExpandedMemory(
                    memory_id=mid, content=content, memory_type=MemoryType.FACT,
                    status=MemoryStatus.ACTIVE, score=0.4, provenance="graph",
                )
            )
            graph_count += 1
        return GraphAwareResult(
            query=query.query, user_id=query.user_id, results=results,
            hybrid_count=len(base.results), graph_count=graph_count,
        )


class FakeContextBuilder:
    """Renders the pre-retrieved candidates into a small ContextPackage."""

    def __init__(self, *, raises: bool = False) -> None:
        self._raises = raises
        self.last_retrieved: list[RetrievedMemory] | None = None

    async def build(self, request: ContextRequest, *, retrieved: list[RetrievedMemory] | None = None) -> ContextPackage:
        if self._raises:
            raise RuntimeError("context build down")
        self.last_retrieved = retrieved
        candidates = retrieved or []
        memories = [
            ContextMemory(
                memory_id=c.memory_id, content=c.content, memory_type=c.memory_type,
                status=c.status, score=c.final_score, tokens=max(1, len(c.content) // 4),
                is_promoted=c.is_promoted,
            )
            for c in candidates
        ]
        text = "\n".join(f"- ({m.memory_type.value}) {m.content}" for m in memories)
        return ContextPackage(
            query=request.query, user_id=request.user_id, memories=memories,
            context_text=text, total_tokens=sum(m.tokens for m in memories),
            max_tokens=request.max_tokens, metadata=request.metadata,
        )


class FakeLLMProvider(LLMProvider):
    def __init__(self, response: str = "the answer", *, raises: bool = False, sleep: float = 0.0) -> None:
        self._response = response
        self._raises = raises
        self._sleep = sleep
        self.calls = 0

    @property
    def model_name(self) -> str:
        return "fake-agent-llm"

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.calls += 1
        if self._sleep:
            import asyncio
            await asyncio.sleep(self._sleep)
        if self._raises:
            raise RuntimeError("llm down")
        return self._response

    async def structured_generate(self, prompt: str, *, schema: dict[str, str], system: str | None = None) -> dict[str, Any]:
        return {}

    async def health_check(self) -> bool:
        return True
