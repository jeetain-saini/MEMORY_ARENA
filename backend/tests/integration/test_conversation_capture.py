"""Integration: conversational memory capture (Stage 15) end-to-end.

Wires the real ingestion + consolidation pipelines (mirroring main.py) against
SQLite + an in-memory graph, with a fake agent runtime so /query "answers"
without an LLM. Verifies: conversation -> memory -> retrievable; capture disabled;
streaming path; failure isolation; duplicate suppression; contradiction edge.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.application.dto.agent_dto import AgentRequest, AgentResponse, AgentTrace
from app.application.interfaces.workflow_job_processor import WorkflowJob, WorkflowJobProcessor
from app.application.services.agent.conversation_capture_policy import ConversationCapturePolicy
from app.application.services.agent.conversation_capture_service import ConversationCaptureService
from app.application.services.consolidation.config import ConsolidationConfig
from app.application.services.consolidation.consolidation_event_handler import (
    ConsolidationEventHandler,
)
from app.application.services.consolidation.persistent_consolidation_service import (
    PersistentConsolidationService,
)
from app.application.services.intelligence_config import IntelligenceConfig
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.application.use_cases.ingest_memory_use_cases_impl import IngestMemoryUseCaseImpl
from app.application.use_cases.query_memory_use_cases_impl import QueryMemoryUseCaseImpl
from app.application.dto.graph_dto import GraphEdgeType
from app.domain.value_objects.memory_status import MemoryStatus
from app.infrastructure.database.session import create_session_factory
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.events.in_process_dispatcher import InProcessEventDispatcher
from app.infrastructure.graph.in_memory_graph_repository import InMemoryGraphRepository
from app.infrastructure.llm.graphs.sequential_consolidation_engine import (
    SequentialConsolidationEngine,
)
from app.infrastructure.llm.graphs.sequential_engine import SequentialExtractionEngine
from app.infrastructure.llm.in_process_consolidation_processor import (
    InProcessConsolidationJobProcessor,
)
from app.infrastructure.llm.in_process_workflow_processor import InProcessWorkflowJobProcessor
from app.infrastructure.llm.providers.deterministic_provider import DeterministicLLMProvider
from tests.integration._db import make_engine, seed_user


def _run(coro_fn):
    return asyncio.run(coro_fn())


class _FakeRuntime:
    async def respond(self, request: AgentRequest) -> AgentResponse:
        return AgentResponse(
            query=request.query, user_id=request.user_id, answer="ok",
            citations=[], trace=AgentTrace(),
        )

    async def _agen(self):
        if False:  # pragma: no cover
            yield None

    def stream(self, request: AgentRequest):
        return self._agen()


class _RaisingProcessor(WorkflowJobProcessor):
    async def submit(self, job: WorkflowJob) -> None:
        raise RuntimeError("queue down")


async def _build(engine, *, enabled: bool = True, capture_processor=None) -> SimpleNamespace:
    factory = create_session_factory(engine)

    def uow_factory() -> SQLAlchemyUnitOfWork:
        return SQLAlchemyUnitOfWork(factory)

    dispatcher = InProcessEventDispatcher()
    provider = DeterministicLLMProvider()

    ingest = IngestMemoryUseCaseImpl(SequentialExtractionEngine(provider), uow_factory, dispatcher)
    wf_proc = InProcessWorkflowJobProcessor(ingest.process)

    graph_repo = InMemoryGraphRepository()

    def _intel() -> MemoryIntelligenceService:
        return MemoryIntelligenceService(uow_factory(), dispatcher, IntelligenceConfig())

    consol = PersistentConsolidationService(
        uow_factory=uow_factory,
        engine=SequentialConsolidationEngine(provider),
        intelligence_service_factory=_intel,
        graph_repo=graph_repo,
        dispatcher=dispatcher,
        config=ConsolidationConfig(),
    )
    consol_proc = InProcessConsolidationJobProcessor(consol.process)
    ConsolidationEventHandler(consol_proc).register(dispatcher)

    capture = ConversationCaptureService(
        capture_processor or wf_proc, ConversationCapturePolicy(), enabled=enabled
    )
    use_case = QueryMemoryUseCaseImpl(_FakeRuntime(), None, None, capture)
    return SimpleNamespace(
        use_case=use_case, wf=wf_proc, consol=consol_proc,
        uow_factory=uow_factory, graph=graph_repo,
    )


async def _active_memories(uow_factory, user_id: UUID):
    async with uow_factory() as uow:
        mems = await uow.memories.list_by_user(user_id, limit=100)
    return [m for m in mems if m.status == MemoryStatus.ACTIVE]


def test_conversation_creates_and_retrieves_memory() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        p = await _build(engine)

        resp = await p.use_case.execute(AgentRequest(user_id=user, query="My name is Jeetain."))
        assert resp.answer == "ok"  # the agent still answered normally
        await p.wf.drain()
        await p.consol.drain()

        active = await _active_memories(p.uow_factory, user)
        assert any("jeetain" in m.content.lower() for m in active), [m.content for m in active]
        await engine.dispose()

    _run(scenario)


def test_capture_disabled_creates_nothing() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        p = await _build(engine, enabled=False)

        await p.use_case.execute(AgentRequest(user_id=user, query="My name is Jeetain."))
        await p.wf.drain()
        await p.consol.drain()

        active = await _active_memories(p.uow_factory, user)
        assert active == []
        await engine.dispose()

    _run(scenario)


def test_noise_turn_is_not_captured() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        p = await _build(engine)

        await p.use_case.execute(AgentRequest(user_id=user, query="What is FastAPI?"))
        await p.wf.drain()
        await p.consol.drain()

        assert await _active_memories(p.uow_factory, user) == []
        await engine.dispose()

    _run(scenario)


def test_streaming_path_captures() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        p = await _build(engine)

        # Consume the stream (scope check + fire-and-forget capture scheduled).
        async for _ in p.use_case.stream(AgentRequest(user_id=user, query="I prefer dark mode.")):
            pass
        await asyncio.sleep(0)  # let the scheduled capture task submit
        await p.wf.drain()
        await p.consol.drain()

        active = await _active_memories(p.uow_factory, user)
        assert any("dark mode" in m.content.lower() for m in active), [m.content for m in active]
        await engine.dispose()

    _run(scenario)


def test_capture_failure_is_isolated() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        p = await _build(engine, capture_processor=_RaisingProcessor())

        # Submit raises inside maybe_capture, but execute must still return.
        resp = await p.use_case.execute(AgentRequest(user_id=user, query="My name is Jeetain."))
        assert resp.answer == "ok"
        await engine.dispose()

    _run(scenario)


def test_duplicate_suppression() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        p = await _build(engine)

        await p.use_case.execute(AgentRequest(user_id=user, query="I use Postgres"))
        await p.use_case.execute(AgentRequest(user_id=user, query="I really use Postgres"))
        await p.wf.drain()        # both memories created + MemoryCreated dispatched
        await p.consol.drain()    # SUPERSEDES archives the older

        active = await _active_memories(p.uow_factory, user)
        # Near-duplicate collapses: only one remains ACTIVE.
        assert len(active) == 1, [m.content for m in active]
        await engine.dispose()

    _run(scenario)


def test_contradiction_creates_edge() -> None:
    async def scenario() -> None:
        engine = await make_engine()
        user = await seed_user(engine)
        p = await _build(engine)

        await p.use_case.execute(AgentRequest(user_id=user, query="I use Postgres"))
        await p.use_case.execute(AgentRequest(user_id=user, query="I no longer use Postgres"))
        await p.wf.drain()
        await p.consol.drain()

        async with p.uow_factory() as uow:
            mems = await uow.memories.list_by_user(user, limit=100)
        edges = []
        for m in mems:
            edges.extend(await p.graph.get_edges(str(m.id)))
        assert any(e.edge_type == GraphEdgeType.CONTRADICTS for e in edges), edges
        await engine.dispose()

    _run(scenario)
