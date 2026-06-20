"""Integration: ContextBuilderService driven by the LLMContextCompressor.

Verifies the LLM compressor plugs into the existing pipeline without breaking
the ContextPackage contract or the token-budget guarantee, and that any failure
degrades gracefully to the heuristic compressor. Offline-first: a fake provider
stands in for the LLM; no network, no API keys.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar
from uuid import uuid4

from app.application.dto.context_dto import ContextRequest
from app.application.interfaces.llm_provider import LLMProvider
from app.application.services.context.compressor import HeuristicContextCompressor
from app.application.services.context.conflict_detector import ConflictDetector
from app.application.services.context.consolidation_service import MemoryConsolidationService
from app.application.services.context.context_builder import ContextBuilderService
from app.application.services.context.selection_service import MemorySelectionService
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.application.services.retrieval.config import RetrievalConfig
from app.application.services.retrieval.hybrid_retriever import HybridRetriever
from app.application.services.retrieval.keyword_retriever import KeywordRetriever
from app.application.services.retrieval.reranker import SimpleCrossEncoderReranker
from app.application.services.retrieval.retrieval_service import MemoryRetrievalService
from app.application.services.retrieval.vector_retriever import VectorRetriever
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.compressors.llm_compressor import LLMContextCompressor
from tests.integration._db import make_engine, seed_user
from tests.integration._retrieval import make_provider, make_uow_factory, save_and_embed

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


class _FakeLLMProvider(LLMProvider):
    def __init__(self, response: str = "", *, raises: bool = False) -> None:
        self._response = response
        self._raises = raises

    @property
    def model_name(self) -> str:
        return "fake"

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        if self._raises:
            raise RuntimeError("provider down")
        return self._response

    async def structured_generate(
        self, prompt: str, *, schema: dict[str, str], system: str | None = None
    ) -> dict[str, Any]:
        return {}

    async def health_check(self) -> bool:
        return True


async def _builder(engine, llm_provider: LLMProvider):
    user_id = await seed_user(engine)
    uow_factory = make_uow_factory(engine)
    provider = make_provider()
    rcfg = RetrievalConfig()
    retrieval = MemoryRetrievalService(
        HybridRetriever(
            VectorRetriever(uow_factory, provider),
            KeywordRetriever(uow_factory, rcfg),
            rcfg,
        ),
        SimpleCrossEncoderReranker(rcfg.rerank_overlap_weight),
    )
    counter = HeuristicTokenCounter()
    compressor = LLMContextCompressor(
        llm_provider, counter, fallback=HeuristicContextCompressor(counter)
    )
    builder = ContextBuilderService(
        retrieval_service=retrieval,
        selection_service=MemorySelectionService(counter),
        consolidation_service=MemoryConsolidationService(),
        conflict_detector=ConflictDetector(),
        compressor=compressor,
    )
    return user_id, uow_factory, provider, builder


def test_build_uses_llm_compressor_when_valid() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        # Valid response: type marker present, preserves the term "python".
        provider = _FakeLLMProvider("[fact] user works with python daily")
        user_id, uow_factory, embed, builder = await _builder(engine, provider)
        await save_and_embed(
            uow_factory, embed,
            Memory.create(user_id=user_id, content="I work with Python", memory_type=MemoryType.FACT),
        )

        package = await builder.build(
            ContextRequest(query="python", user_id=user_id, max_tokens=2000)
        )
        assert package.context_text == "[fact] user works with python daily"
        assert package.total_tokens <= package.max_tokens
        await engine.dispose()

    _run(scenario)


def test_build_falls_back_gracefully_on_error() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        provider = _FakeLLMProvider(raises=True)
        user_id, uow_factory, embed, builder = await _builder(engine, provider)
        await save_and_embed(
            uow_factory, embed,
            Memory.create(user_id=user_id, content="Paris is the capital of France", memory_type=MemoryType.FACT),
        )

        package = await builder.build(
            ContextRequest(query="paris", user_id=user_id, max_tokens=2000)
        )
        # Heuristic fallback rendered the original content.
        assert "Paris is the capital of France" in package.context_text
        assert package.total_tokens <= package.max_tokens
        await engine.dispose()

    _run(scenario)


def test_budget_enforced_end_to_end_llm_path() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        # Oversized LLM response → validation rejects → heuristic fallback.
        provider = _FakeLLMProvider("[fact] " + "verbose padding " * 100)
        user_id, uow_factory, embed, builder = await _builder(engine, provider)
        for i in range(4):
            await save_and_embed(
                uow_factory, embed,
                Memory.create(user_id=user_id, content=f"memory {i} about alpha topic", memory_type=MemoryType.FACT),
            )

        package = await builder.build(
            ContextRequest(query="alpha", user_id=user_id, max_tokens=10)
        )
        assert package.total_tokens <= 10
        await engine.dispose()

    _run(scenario)


def test_debug_includes_compression_stats_on_llm_path() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        provider = _FakeLLMProvider("[fact] short summary about the sky")
        user_id, uow_factory, embed, builder = await _builder(engine, provider)
        await save_and_embed(
            uow_factory, embed,
            Memory.create(user_id=user_id, content="The sky is blue on a clear day", memory_type=MemoryType.FACT),
        )

        debug = await builder.debug(
            ContextRequest(query="sky", user_id=user_id, max_tokens=2000)
        )
        assert debug.compression.compressed_tokens <= debug.package.max_tokens
        assert debug.compression.original_tokens > 0
        assert debug.package.context_text == "[fact] short summary about the sky"
        await engine.dispose()

    _run(scenario)


def test_provenance_preserved_through_llm_path() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        provider = _FakeLLMProvider("[goal] user wants to ship the product soon")
        user_id, uow_factory, embed, builder = await _builder(engine, provider)
        memory = Memory.create(
            user_id=user_id, content="I want to ship the product", memory_type=MemoryType.GOAL
        )
        await save_and_embed(uow_factory, embed, memory)

        package = await builder.build(
            ContextRequest(query="ship product", user_id=user_id, max_tokens=2000)
        )
        # memory_id + memory_type provenance survives compression.
        assert any(m.memory_id == memory.id for m in package.memories)
        assert any(m.memory_type is MemoryType.GOAL for m in package.memories)
        await engine.dispose()

    _run(scenario)
