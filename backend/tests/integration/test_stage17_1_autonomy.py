"""Stage 17.1 autonomy integration tests.

Proves the self-evolving loop runs without manual endpoint calls:
  * the retrieval tracker evolves + persists importance from retrieval_count;
  * the MemoryCreated event handler auto-promotes recurring episodic memories;
  * the periodic maintenance job runs importance + promotion + clustering +
    forgetting across tenants.

SQLite + in-memory graph + dispatcher (same harness as test_stage17_intelligence).
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import TypeVar
from uuid import UUID

from app.application.interfaces.intelligence_job_processor import IntelligenceJob
from app.application.services.intelligence.clustering_engine import ClusteringEngine
from app.application.services.intelligence.evolving_retrieval_tracker import (
    EvolvingRetrievalTracker,
)
from app.application.services.intelligence.intelligence_event_handler import (
    IntelligenceEventHandler,
)
from app.application.services.intelligence.maintenance_job import (
    MemoryIntelligenceMaintenanceJob,
)
from app.application.services.intelligence.promotion_engine import PromotionEngine
from app.domain.entities.memory import Memory
from app.domain.entities.memory_score import MemoryScore
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.intelligence.in_process_processor import (
    InProcessIntelligenceJobProcessor,
)
from app.infrastructure.scheduler.in_process_scheduler import InProcessScheduler
from tests.integration._db import make_engine, seed_user

T = TypeVar("T")


def _run(coro_fn: Callable[[], Awaitable[T]]) -> T:
    return asyncio.run(coro_fn())


def _factory(engine) -> Callable[[], SQLAlchemyUnitOfWork]:
    sf = create_session_factory(engine)
    return lambda: SQLAlchemyUnitOfWork(sf)


async def _save(uow_factory, memory: Memory) -> None:
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()


# --- 1. retrieval tracker evolves + persists importance --------------------

def test_retrieval_tracker_evolves_and_persists_importance() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        hot = Memory.create(user_id=user, content="frequently used fact",
                            memory_type=MemoryType.FACT)
        cold = Memory.create(user_id=user, content="rarely used fact",
                             memory_type=MemoryType.FACT)
        await _save(uowf, hot)
        await _save(uowf, cold)

        tracker = EvolvingRetrievalTracker(uowf)
        for _ in range(8):          # hot retrieved many times
            await tracker.record([hot.id])
        await tracker.record([cold.id])  # cold retrieved once

        async with uowf() as uow:
            hot_after = await uow.memories.get_by_id(hot.id)
            cold_after = await uow.memories.get_by_id(cold.id)

        # retrieval_count persisted, importance evolved (mutated, not static).
        assert hot_after.retrieval_count == 8
        assert cold_after.retrieval_count == 1
        assert hot_after.last_retrieved_at is not None
        # the more-retrieved memory evolves to a higher importance.
        assert hot_after.score.importance > cold_after.score.importance
        await engine.dispose()

    _run(scenario)


# --- 2. MemoryCreated -> auto promotion (no API call) ----------------------

def test_memory_created_event_auto_promotes() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        dispatcher = InProcessEventDispatcher()

        promotion = PromotionEngine(uowf, graph, dispatcher)
        clustering = ClusteringEngine(uowf, graph)

        async def runner(job: IntelligenceJob) -> None:
            await promotion.promote_user(job.user_id)
            await clustering.cluster_user(job.user_id)

        processor = InProcessIntelligenceJobProcessor(runner)
        IntelligenceEventHandler(processor).register(dispatcher)

        # seed three recurring episodic memories (the promotion trigger).
        for _ in range(3):
            await _save(uowf, Memory.create(user_id=user, content="I am learning Rust",
                                            memory_type=MemoryType.EXPERIENCE))
        # fire one MemoryCreated -> handler submits a job -> processor runs it.
        await dispatcher.dispatch(
            (await _new_created_event(uowf, user)),
        )
        await processor.drain()

        async with uowf() as uow:
            all_mem = await uow.memories.list_for_analytics(user)
        semantic = [m for m in all_mem if m.category is MemoryCategory.SEMANTIC
                    and m.memory_type is MemoryType.SKILL]
        assert len(semantic) >= 1  # promotion happened automatically
        await engine.dispose()

    _run(scenario)


async def _new_created_event(uowf, user: UUID):
    """Create one more episodic memory and return its pending MemoryCreated event."""
    mem = Memory.create(user_id=user, content="I am learning Rust",
                        memory_type=MemoryType.EXPERIENCE)
    await _save(uowf, mem)
    return mem.pull_events()


# --- 3. periodic maintenance job runs all four engines ---------------------

def test_maintenance_job_runs_full_cycle() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        dispatcher = InProcessEventDispatcher()

        # (a) recurring episodic -> promotable
        for _ in range(3):
            await _save(uowf, Memory.create(user_id=user, content="learning LangGraph daily",
                                            memory_type=MemoryType.EXPERIENCE))
        # (b) related cluster pair
        await _save(uowf, Memory.create(user_id=user,
                                        content="PostgreSQL Neo4j Redis datastores",
                                        memory_type=MemoryType.FACT))
        await _save(uowf, Memory.create(user_id=user,
                                        content="Redis cache alongside PostgreSQL",
                                        memory_type=MemoryType.FACT))
        # (c) stale, isolated, low-importance -> forgettable
        old = datetime.now(timezone.utc) - timedelta(days=200)
        stale = Memory(user_id=user, content="zzz obscure ancient trivia xyz",
                       memory_type=MemoryType.FACT,
                       score=MemoryScore(importance=0.05, utility=0.1, frequency=0.0,
                                         recency=0.0, confidence=0.3),
                       created_at=old, updated_at=old)
        await _save(uowf, stale)

        job = MemoryIntelligenceMaintenanceJob(uowf, graph, dispatcher)
        result = await job.run_cycle(user_id=user)

        assert result.promoted >= 1     # promotion ran
        assert result.clustered >= 1    # clustering ran
        assert result.forgotten >= 1    # forgetting ran

        async with uowf() as uow:
            stale_after = await uow.memories.get_by_id(stale.id)
        assert stale_after.status is MemoryStatus.FORGOTTEN
        await engine.dispose()

    _run(scenario)


def test_scheduler_ticker_runs_forgetting_automatically() -> None:
    """End-to-end autonomy proof: the interval ticker -> run_all -> maintenance
    job -> ForgettingEngine forgets a stale memory with no manual call."""

    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        dispatcher = InProcessEventDispatcher()
        old = datetime.now(timezone.utc) - timedelta(days=200)
        stale = Memory(user_id=user, content="zzz obscure ancient trivia xyz",
                       memory_type=MemoryType.FACT,
                       score=MemoryScore(importance=0.05, utility=0.1, frequency=0.0,
                                         recency=0.0, confidence=0.3),
                       created_at=old, updated_at=old)
        await _save(uowf, stale)

        scheduler = InProcessScheduler(interval_seconds=0.02)
        scheduler.register(
            MemoryIntelligenceMaintenanceJob(uowf, graph, dispatcher), cron="0 2 * * *"
        )
        await scheduler.start()  # ticker starts because interval > 0
        try:
            for _ in range(50):  # poll up to ~1s for an automatic tick
                await asyncio.sleep(0.02)
                async with uowf() as uow:
                    m = await uow.memories.get_by_id(stale.id)
                if m.status is MemoryStatus.FORGOTTEN:
                    break
        finally:
            await scheduler.stop()

        async with uowf() as uow:
            final = await uow.memories.get_by_id(stale.id)
        assert final.status is MemoryStatus.FORGOTTEN  # forgotten by the ticker, no API call
        await engine.dispose()

    _run(scenario)


def test_maintenance_job_is_idempotent() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        uowf = _factory(engine)
        graph = InMemoryGraphRepository()
        dispatcher = InProcessEventDispatcher()
        for _ in range(3):
            await _save(uowf, Memory.create(user_id=user, content="learning LangGraph daily",
                                            memory_type=MemoryType.EXPERIENCE))

        job = MemoryIntelligenceMaintenanceJob(uowf, graph, dispatcher)
        first = await job.run_cycle(user_id=user)
        second = await job.run_cycle(user_id=user)
        assert first.promoted == 1
        assert second.promoted == 0  # already promoted -> no double promotion
        await engine.dispose()

    _run(scenario)
