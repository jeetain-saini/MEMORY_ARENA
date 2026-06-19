"""Integration: IngestMemoryUseCase -> single write path -> event pipeline.

Drives the deterministic extraction engine against SQLite and asserts that
extracted memories are persisted through CreateMemoryUseCase, that the
embedding + graph side effects fire (via the same dispatcher used in production),
and that importance/confidence/workflow_version flow into the created memory.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.application.dto.extraction_dto import ExtractionRequest
from app.application.services.embedding_event_handler import EmbeddingEventHandler
from app.application.services.embedding_service import EmbeddingService
from app.application.services.graph.config import GraphConfig
from app.application.services.graph.event_handler import GraphEventHandler
from app.application.services.graph.relationship_service import GraphRelationshipService
from app.application.services.graph.sync_service import GraphSyncService
from app.application.use_cases.ingest_memory_use_cases_impl import IngestMemoryUseCaseImpl
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.embeddings.deterministic_provider import DeterministicEmbeddingProvider
from app.infrastructure.embeddings.in_process_processor import InProcessEmbeddingJobProcessor
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.graph.in_process_processor import InProcessGraphJobProcessor
from app.infrastructure.llm.graphs.extraction_steps import WORKFLOW_VERSION
from app.infrastructure.llm.graphs.sequential_engine import SequentialExtractionEngine
from app.infrastructure.llm.providers.deterministic_provider import DeterministicLLMProvider
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


async def _wire():
    engine = await make_engine()
    user_id = await seed_user(engine)
    factory = create_session_factory(engine)

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    dispatcher = InProcessEventDispatcher()

    # Side-effect pipelines on the same dispatcher the ingest use case dispatches to.
    embed_service = EmbeddingService(uow_factory, DeterministicEmbeddingProvider(dimensions=8))
    embed_processor = InProcessEmbeddingJobProcessor(embed_service.process)
    EmbeddingEventHandler(embed_processor).register(dispatcher)

    graph_repo = InMemoryGraphRepository()
    graph_config = GraphConfig()
    graph_sync = GraphSyncService(
        uow_factory, graph_repo, GraphRelationshipService(graph_config), graph_config
    )
    graph_processor = InProcessGraphJobProcessor(graph_sync.process)
    GraphEventHandler(graph_processor).register(dispatcher)

    ingest = IngestMemoryUseCaseImpl(
        engine=SequentialExtractionEngine(DeterministicLLMProvider()),
        uow_factory=uow_factory,
        dispatcher=dispatcher,
    )
    return engine, uow_factory, ingest, embed_processor, graph_processor, graph_repo, user_id


def test_ingest_persists_extracted_memories() -> None:
    async def scenario() -> None:
        engine, uow_factory, ingest, *_rest, user_id = await _wire()
        summary = await ingest.execute(
            ExtractionRequest(user_id=user_id, raw_text="I prefer dark mode. I want to ship the project.")
        )
        assert summary.extracted_count == 2
        assert len(summary.created_ids) == 2
        assert summary.workflow_version == WORKFLOW_VERSION

        async with uow_factory() as uow:
            stored = await uow.memories.list_by_user(user_id, limit=50)
        assert len(stored) == 2
        await engine.dispose()

    _run(scenario)


def test_ingest_flows_importance_confidence_and_version_into_memory() -> None:
    async def scenario() -> None:
        engine, uow_factory, ingest, *_rest, user_id = await _wire()
        summary = await ingest.execute(
            ExtractionRequest(user_id=user_id, raw_text="I prefer concise answers.")
        )
        memory_id = summary.created_ids[0]
        async with uow_factory() as uow:
            memory = await uow.memories.get_by_id(memory_id)
        assert memory is not None
        # Confidence flowed from the deterministic estimate (no hedging -> 0.8).
        assert memory.score.confidence == 0.8
        assert 0.0 <= memory.score.importance <= 1.0
        assert memory.metadata["workflow_version"] == WORKFLOW_VERSION
        await engine.dispose()

    _run(scenario)


def test_ingest_triggers_embedding_and_graph_pipelines() -> None:
    async def scenario() -> None:
        (engine, uow_factory, ingest, embed_processor, graph_processor, graph_repo, user_id) = await _wire()
        summary = await ingest.execute(
            ExtractionRequest(user_id=user_id, raw_text="I prefer dark mode. I want to ship the project.")
        )
        # Side effects run off the dispatch; drain to observe them deterministically.
        await embed_processor.drain()
        await graph_processor.drain()

        async with uow_factory() as uow:
            for mid in summary.created_ids:
                assert await uow.embeddings.get_embedding(mid) is not None
        for mid in summary.created_ids:
            assert await graph_repo.get_node(str(mid)) is not None
        await engine.dispose()

    _run(scenario)


def test_ingest_trivial_text_creates_nothing() -> None:
    async def scenario() -> None:
        engine, uow_factory, ingest, *_rest, user_id = await _wire()
        summary = await ingest.execute(ExtractionRequest(user_id=user_id, raw_text="hi"))
        assert summary.extracted_count == 0 and summary.created_ids == []
        await engine.dispose()

    _run(scenario)
