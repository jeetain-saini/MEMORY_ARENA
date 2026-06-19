"""Integration tests for the end-to-end MemoryRetrievalService pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.dto.retrieval_dto import MemorySearchQuery
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


async def _service(engine):
    user_id = await seed_user(engine)
    uow_factory = make_uow_factory(engine)
    provider = make_provider()
    config = RetrievalConfig()
    hybrid = HybridRetriever(
        VectorRetriever(uow_factory, provider),
        KeywordRetriever(uow_factory, config),
        config,
    )
    service = MemoryRetrievalService(hybrid, SimpleCrossEncoderReranker(config.rerank_overlap_weight))
    return user_id, uow_factory, provider, service


def test_search_returns_relevant_first_and_respects_top_k() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id, uow_factory, provider, service = await _service(engine)

        relevant = Memory.create(user_id=user_id, content="vector databases and pgvector", memory_type=MemoryType.FACT)
        for content in ("lunch with sam", "renew passport", "call the bank"):
            await save_and_embed(uow_factory, provider, Memory.create(user_id=user_id, content=content, memory_type=MemoryType.FACT))
        await save_and_embed(uow_factory, provider, relevant)

        query = MemorySearchQuery(query="vector databases and pgvector", user_id=user_id, top_k=2)
        result = await service.search(query)
        assert result.count == 2
        assert result.results[0].memory_id == relevant.id
        await engine.dispose()

    _run(scenario)


def test_debug_returns_all_candidates_with_breakdown() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id, uow_factory, provider, service = await _service(engine)
        for content in ("alpha note", "beta note", "gamma note"):
            await save_and_embed(uow_factory, provider, Memory.create(user_id=user_id, content=content, memory_type=MemoryType.FACT))

        result = await service.debug(MemorySearchQuery(query="alpha note", user_id=user_id, top_k=1))
        # debug ignores top_k truncation -> all fused candidates returned
        assert result.count == 3
        first = result.results[0]
        assert first.scores.final_score == first.final_score
        await engine.dispose()

    _run(scenario)


def test_search_empty_corpus_returns_no_results() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user_id, _uf, _p, service = await _service(engine)
        result = await service.search(MemorySearchQuery(query="anything", user_id=user_id))
        assert result.count == 0
        await engine.dispose()

    _run(scenario)
