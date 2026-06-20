"""Integration: PersistentConsolidationService against SQLite + in-memory graph.

Covers the SUPERSEDES and CONTRADICTS action paths, graceful no-ops, confidence
threshold enforcement, and event dispatch.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.application.dto.consolidation_dto import (
    ConsolidationDecision,
    ConsolidationDecisionType,
    ConsolidationRequest,
)
from app.application.interfaces.consolidation_engine import ConsolidationEngine
from app.application.interfaces.consolidation_job_processor import ConsolidationJob
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.services.consolidation.config import ConsolidationConfig
from app.application.services.consolidation.persistent_consolidation_service import (
    PersistentConsolidationService,
)
from app.application.services.intelligence_config import IntelligenceConfig
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.domain.entities.memory import Memory
from app.domain.events.memory_events import DomainEvent, MemoryConflictFound, MemorySuperseded
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from tests.integration._db import make_engine, seed_user


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Spy dispatcher — records dispatched events
# ---------------------------------------------------------------------------

class _SpyDispatcher(EventDispatcher):
    def __init__(self) -> None:
        self.events: list[DomainEvent] = []

    def register(self, event_type, handler) -> None:  # type: ignore[override]
        pass

    async def dispatch(self, events) -> None:
        self.events.extend(events)


# ---------------------------------------------------------------------------
# Engines that return deterministic decisions for testing
# ---------------------------------------------------------------------------

class _FixedEngine(ConsolidationEngine):
    """Returns a pre-set list of decisions regardless of request."""

    def __init__(self, decisions: list[ConsolidationDecision]) -> None:
        self._decisions = decisions

    async def consolidate(self, request: ConsolidationRequest) -> list[ConsolidationDecision]:
        return self._decisions


class _UniqueEngine(ConsolidationEngine):
    async def consolidate(self, request: ConsolidationRequest) -> list[ConsolidationDecision]:
        return []


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------

async def _setup(config: ConsolidationConfig | None = None):
    engine = await make_engine()
    user_id = await seed_user(engine)
    factory = create_session_factory(engine)

    def uow_factory():
        return SQLAlchemyUnitOfWork(factory)

    def intelligence_factory():
        return MemoryIntelligenceService(
            uow=SQLAlchemyUnitOfWork(factory),
            dispatcher=_SpyDispatcher(),
            config=IntelligenceConfig(),
        )

    dispatcher = _SpyDispatcher()
    graph_repo = InMemoryGraphRepository()

    return engine, uow_factory, intelligence_factory, dispatcher, graph_repo, user_id


async def _save(uow_factory, user_id: UUID, content: str) -> Memory:
    memory = Memory.create(user_id=user_id, content=content, memory_type=MemoryType.FACT)
    async with uow_factory() as uow:
        await uow.memories.save(memory)
        await uow.commit()
    return memory


def _service(
    uow_factory,
    consolidation_engine: ConsolidationEngine,
    intelligence_factory,
    graph_repo: InMemoryGraphRepository,
    dispatcher: _SpyDispatcher,
    config: ConsolidationConfig | None = None,
) -> PersistentConsolidationService:
    return PersistentConsolidationService(
        uow_factory=uow_factory,
        engine=consolidation_engine,
        intelligence_service_factory=intelligence_factory,
        graph_repo=graph_repo,
        dispatcher=dispatcher,
        config=config or ConsolidationConfig(),
    )


# ---------------------------------------------------------------------------
# Tests — SUPERSEDES path
# ---------------------------------------------------------------------------

def test_supersedes_archives_older_memory() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()
        old = await _save(uow_factory, user_id, "I use Python for data science projects")
        new_mem = await _save(uow_factory, user_id, "I use Python for data science")

        decisions = [
            ConsolidationDecision(
                decision_type=ConsolidationDecisionType.SUPERSEDES,
                target_id=old.id,
                reasoning="new is more detailed",
                confidence=0.85,  # above supersede threshold (0.80)
            )
        ]
        svc = _service(uow_factory, _FixedEngine(decisions), intel_factory, graph_repo, dispatcher)
        summary = await svc.process(ConsolidationJob(memory_id=new_mem.id, user_id=user_id))

        # Old memory should now be ARCHIVED.
        async with uow_factory() as uow:
            archived = await uow.memories.get_by_id(old.id)
        assert archived is not None and archived.status == MemoryStatus.ARCHIVED

        # Summary should include the SUPERSEDES decision.
        assert any(d.decision_type == ConsolidationDecisionType.SUPERSEDES for d in summary.decisions)
        await engine.dispose()

    _run(scenario())


def test_supersedes_dispatches_memory_superseded_event() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()
        old = await _save(uow_factory, user_id, "I use Python")
        new_mem = await _save(uow_factory, user_id, "I use Python for data science work daily")

        decisions = [
            ConsolidationDecision(
                decision_type=ConsolidationDecisionType.SUPERSEDES,
                target_id=old.id,
                reasoning="new is longer",
                confidence=0.90,
            )
        ]
        svc = _service(uow_factory, _FixedEngine(decisions), intel_factory, graph_repo, dispatcher)
        await svc.process(ConsolidationJob(memory_id=new_mem.id, user_id=user_id))

        superseded_events = [e for e in dispatcher.events if isinstance(e, MemorySuperseded)]
        assert len(superseded_events) == 1
        assert superseded_events[0].memory_id == old.id
        assert superseded_events[0].superseded_by_id == new_mem.id
        await engine.dispose()

    _run(scenario())


def test_supersedes_below_threshold_does_not_archive() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()
        old = await _save(uow_factory, user_id, "I use Python")
        new_mem = await _save(uow_factory, user_id, "I use Python daily")

        decisions = [
            ConsolidationDecision(
                decision_type=ConsolidationDecisionType.SUPERSEDES,
                target_id=old.id,
                reasoning="new is longer",
                confidence=0.70,  # below supersede threshold (0.80)
            )
        ]
        svc = _service(uow_factory, _FixedEngine(decisions), intel_factory, graph_repo, dispatcher)
        await svc.process(ConsolidationJob(memory_id=new_mem.id, user_id=user_id))

        # old should remain ACTIVE.
        async with uow_factory() as uow:
            still_active = await uow.memories.get_by_id(old.id)
        assert still_active is not None and still_active.status == MemoryStatus.ACTIVE
        assert not any(isinstance(e, MemorySuperseded) for e in dispatcher.events)
        await engine.dispose()

    _run(scenario())


# ---------------------------------------------------------------------------
# Tests — CONTRADICTS path
# ---------------------------------------------------------------------------

def test_contradicts_writes_graph_edge() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()
        mem_a = await _save(uow_factory, user_id, "I love Python")
        mem_b = await _save(uow_factory, user_id, "I hate Python")

        decisions = [
            ConsolidationDecision(
                decision_type=ConsolidationDecisionType.CONTRADICTS,
                target_id=mem_a.id,
                reasoning="opposing stance on Python",
                confidence=0.75,  # above contradict threshold (0.60)
            )
        ]
        svc = _service(uow_factory, _FixedEngine(decisions), intel_factory, graph_repo, dispatcher)
        await svc.process(ConsolidationJob(memory_id=mem_b.id, user_id=user_id))

        from app.application.dto.graph_dto import GraphEdgeType
        edges = await graph_repo.get_edges(str(mem_b.id))
        assert any(e.edge_type == GraphEdgeType.CONTRADICTS for e in edges)
        await engine.dispose()

    _run(scenario())


def test_contradicts_dispatches_conflict_found_event() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()
        mem_a = await _save(uow_factory, user_id, "I love Python")
        mem_b = await _save(uow_factory, user_id, "I hate Python")

        decisions = [
            ConsolidationDecision(
                decision_type=ConsolidationDecisionType.CONTRADICTS,
                target_id=mem_a.id,
                reasoning="opposing stance",
                confidence=0.80,
            )
        ]
        svc = _service(uow_factory, _FixedEngine(decisions), intel_factory, graph_repo, dispatcher)
        await svc.process(ConsolidationJob(memory_id=mem_b.id, user_id=user_id))

        conflict_events = [e for e in dispatcher.events if isinstance(e, MemoryConflictFound)]
        assert len(conflict_events) == 1
        assert conflict_events[0].memory_id_a == mem_b.id
        assert conflict_events[0].memory_id_b == mem_a.id
        await engine.dispose()

    _run(scenario())


def test_contradicts_below_threshold_no_edge() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()
        mem_a = await _save(uow_factory, user_id, "I love Python")
        mem_b = await _save(uow_factory, user_id, "I hate Python")

        decisions = [
            ConsolidationDecision(
                decision_type=ConsolidationDecisionType.CONTRADICTS,
                target_id=mem_a.id,
                reasoning="opposing stance",
                confidence=0.45,  # below contradict threshold (0.60)
            )
        ]
        svc = _service(uow_factory, _FixedEngine(decisions), intel_factory, graph_repo, dispatcher)
        await svc.process(ConsolidationJob(memory_id=mem_b.id, user_id=user_id))

        edges = await graph_repo.get_edges(str(mem_b.id))
        assert edges == []
        assert not any(isinstance(e, MemoryConflictFound) for e in dispatcher.events)
        await engine.dispose()

    _run(scenario())


# ---------------------------------------------------------------------------
# Tests — UNIQUE and MERGE paths
# ---------------------------------------------------------------------------

def test_unique_no_action() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()
        mem_a = await _save(uow_factory, user_id, "I love Python")
        mem_b = await _save(uow_factory, user_id, "gardening is peaceful")

        svc = _service(uow_factory, _UniqueEngine(), intel_factory, graph_repo, dispatcher)
        summary = await svc.process(ConsolidationJob(memory_id=mem_b.id, user_id=user_id))

        assert summary.decisions == []
        assert dispatcher.events == []
        edges = await graph_repo.get_edges(str(mem_b.id))
        assert edges == []
        await engine.dispose()

    _run(scenario())


def test_merge_decision_is_informational_only() -> None:
    """MERGE decisions are included in the summary but no action is taken in Phase 2."""

    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()
        mem_a = await _save(uow_factory, user_id, "I use Python")
        mem_b = await _save(uow_factory, user_id, "Python usage")

        decisions = [
            ConsolidationDecision(
                decision_type=ConsolidationDecisionType.MERGE,
                target_id=mem_a.id,
                reasoning="should be merged",
                confidence=0.70,
            )
        ]
        svc = _service(uow_factory, _FixedEngine(decisions), intel_factory, graph_repo, dispatcher)
        summary = await svc.process(ConsolidationJob(memory_id=mem_b.id, user_id=user_id))

        # Returned in summary.
        assert any(d.decision_type == ConsolidationDecisionType.MERGE for d in summary.decisions)
        # But no events dispatched and no graph edges written.
        assert dispatcher.events == []
        edges = await graph_repo.get_edges(str(mem_b.id))
        assert edges == []

        # Old memory is NOT archived.
        async with uow_factory() as uow:
            still_active = await uow.memories.get_by_id(mem_a.id)
        assert still_active is not None and still_active.status == MemoryStatus.ACTIVE
        await engine.dispose()

    _run(scenario())


# ---------------------------------------------------------------------------
# Tests — graceful no-op
# ---------------------------------------------------------------------------

def test_missing_memory_is_graceful_noop() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()

        svc = _service(uow_factory, _UniqueEngine(), intel_factory, graph_repo, dispatcher)
        summary = await svc.process(ConsolidationJob(memory_id=uuid4(), user_id=user_id))

        assert summary.total_candidates == 0
        assert summary.decisions == []
        await engine.dispose()

    _run(scenario())


def test_summary_contains_correct_metadata() -> None:
    async def scenario() -> None:
        engine, uow_factory, intel_factory, dispatcher, graph_repo, user_id = await _setup()
        mem = await _save(uow_factory, user_id, "test content")

        svc = _service(uow_factory, _UniqueEngine(), intel_factory, graph_repo, dispatcher)
        summary = await svc.process(ConsolidationJob(memory_id=mem.id, user_id=user_id))

        assert summary.new_memory_id == mem.id
        assert summary.user_id == user_id
        assert summary.workflow_version == "consolidation-v1"
        await engine.dispose()

    _run(scenario())
