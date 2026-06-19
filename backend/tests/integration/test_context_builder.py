"""Integration tests for the end-to-end ContextBuilderService pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.dto.context_dto import ContextRequest
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
from tests.integration._db import make_engine, seed_user
from tests.integration._retrieval import make_provider, make_uow_factory, save_and_embed

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _builder(engine):
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
    builder = ContextBuilderService(
        retrieval_service=retrieval,
        selection_service=MemorySelectionService(counter),
        consolidation_service=MemoryConsolidationService(),
        conflict_detector=ConflictDetector(),
        compressor=HeuristicContextCompressor(counter),
    )
    return user_id, uow_factory, provider, builder


def test_build_produces_package_within_budget() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id, uow_factory, provider, builder = await _builder(engine)
        for content in ("python is a programming language", "the cat sat on the mat", "paris is in france"):
            await save_and_embed(uow_factory, provider, Memory.create(user_id=user_id, content=content, memory_type=MemoryType.FACT))

        package = await builder.build(ContextRequest(query="python programming", user_id=user_id, max_tokens=2000))
        assert package.memories
        assert package.total_tokens <= package.max_tokens
        assert package.context_text != ""
        await engine.dispose()

    _run(scenario)


def test_build_enforces_small_budget() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id, uow_factory, provider, builder = await _builder(engine)
        for i in range(5):
            await save_and_embed(uow_factory, provider, Memory.create(user_id=user_id, content=f"memory number {i} about alpha", memory_type=MemoryType.FACT))

        package = await builder.build(ContextRequest(query="alpha", user_id=user_id, max_tokens=8))
        assert package.total_tokens <= 8
        await engine.dispose()

    _run(scenario)


def test_debug_reports_conflicts() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id, uow_factory, provider, builder = await _builder(engine)
        await save_and_embed(uow_factory, provider, Memory.create(user_id=user_id, content="I use Python", memory_type=MemoryType.PREFERENCE))
        await save_and_embed(uow_factory, provider, Memory.create(user_id=user_id, content="I no longer use Python", memory_type=MemoryType.PREFERENCE))

        debug = await builder.debug(ContextRequest(query="python", user_id=user_id, max_tokens=2000))
        assert len(debug.conflicts) >= 1
        assert debug.compression.original_tokens >= debug.compression.compressed_tokens
        await engine.dispose()

    _run(scenario)


def test_debug_reports_consolidation_of_duplicates() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id, uow_factory, provider, builder = await _builder(engine)
        # Two identical memories -> one should be consolidated away.
        for _ in range(2):
            await save_and_embed(uow_factory, provider, Memory.create(user_id=user_id, content="the sky is blue today", memory_type=MemoryType.FACT))

        debug = await builder.debug(ContextRequest(query="sky", user_id=user_id, max_tokens=2000))
        dropped_reasons = {d.reason for d in debug.dropped}
        assert "duplicate" in dropped_reasons or len(debug.consolidations) >= 1
        await engine.dispose()

    _run(scenario)
