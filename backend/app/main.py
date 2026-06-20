"""Application entrypoint and composition root.

`create_app()` is the factory that assembles the FastAPI application:
configuration, logging, middleware, exception handlers, routers, and the
startup/shutdown lifecycle that owns the datastore connections. Keeping all
wiring here (rather than scattered at import time) makes the boot sequence
explicit and the app re-creatable in tests.

Startup order: configure logging -> connect Postgres -> Redis -> Neo4j.
Shutdown unwinds in reverse so dependents close before their dependencies.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.application.services.consolidation.config import ConsolidationConfig
from app.application.services.consolidation.consolidation_event_handler import (
    ConsolidationEventHandler,
)
from app.application.services.consolidation.persistent_consolidation_service import (
    PersistentConsolidationService,
)
from app.application.services.embedding_event_handler import EmbeddingEventHandler
from app.application.services.embedding_service import EmbeddingService
from app.application.services.graph.config import GraphConfig
from app.application.services.graph.event_handler import GraphEventHandler
from app.application.services.graph.relationship_service import GraphRelationshipService
from app.application.services.graph.sync_service import GraphSyncService
from app.application.services.intelligence_config import IntelligenceConfig
from app.application.services.maintenance.config import MaintenanceConfig
from app.application.services.maintenance.inference_event_handler import InferenceEventHandler
from app.application.services.maintenance.memory_summary_service import MemorySummaryService
from app.application.services.maintenance.relationship_inference_service import (
    RelationshipInferenceService,
)
from app.application.services.maintenance.summary_refresh_job import SummaryRefreshJob
from app.application.services.maintenance.sweeps import (
    ArchivalSweepJob,
    DecaySweepJob,
    PromotionSweepJob,
)
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.application.use_cases.ingest_memory_use_cases_impl import IngestMemoryUseCaseImpl
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import RequestContextLogMiddleware, configure_logging
from app.infrastructure.cache.redis import redis_manager
from app.infrastructure.database.postgres import postgres_manager
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.embeddings.factory import build_embedding_provider
from app.infrastructure.embeddings.in_process_processor import InProcessEmbeddingJobProcessor
from app.infrastructure.events.in_process_dispatcher import in_process_dispatcher
from app.infrastructure.graph.factory import build_graph_repository
from app.infrastructure.graph.in_process_processor import InProcessGraphJobProcessor
from app.infrastructure.graph.neo4j import neo4j_manager
from app.infrastructure.llm.graphs.factory import build_consolidation_engine, build_workflow_engine
from app.infrastructure.llm.in_process_consolidation_processor import (
    InProcessConsolidationJobProcessor,
)
from app.infrastructure.llm.in_process_maintenance_processor import (
    InProcessMaintenanceJobProcessor,
)
from app.infrastructure.llm.in_process_workflow_processor import InProcessWorkflowJobProcessor
from app.infrastructure.scheduler.in_process_scheduler import InProcessScheduler
from app.infrastructure.summaries.deterministic_summary_generator import (
    DeterministicSummaryGenerator,
)

_logger = logging.getLogger("memoryarena.lifecycle")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Manage the application's startup and shutdown lifecycle."""
    settings: Settings = app.state.settings

    # --- Startup: bring datastore connections online (fail fast) ----------
    _logger.info("startup.begin", extra={"environment": settings.app_env})
    await postgres_manager.connect(settings)
    await redis_manager.connect(settings)
    await neo4j_manager.connect(settings)

    # --- Wire the event-driven embedding pipeline ------------------------
    embedding_service = EmbeddingService(
        uow_factory=lambda: SQLAlchemyUnitOfWork(postgres_manager.sessionmaker),
        provider=build_embedding_provider(),
    )
    embedding_processor = InProcessEmbeddingJobProcessor(embedding_service.process)
    EmbeddingEventHandler(embedding_processor).register(in_process_dispatcher)
    app.state.embedding_processor = embedding_processor

    # --- Wire the event-driven knowledge-graph sync ----------------------
    # Sync runs off the request path via a background job processor (mirrors
    # the embedding pipeline), drained on shutdown for graceful completion.
    graph_config = GraphConfig()
    graph_sync = GraphSyncService(
        uow_factory=lambda: SQLAlchemyUnitOfWork(postgres_manager.sessionmaker),
        repository=build_graph_repository(),
        relationship_service=GraphRelationshipService(graph_config),
        config=graph_config,
    )
    graph_processor = InProcessGraphJobProcessor(graph_sync.process)
    GraphEventHandler(graph_processor).register(in_process_dispatcher)
    app.state.graph_processor = graph_processor

    # --- Wire the async memory-extraction (ingestion) pipeline -----------
    # The ingest use case creates memories through the single write path, so
    # MemoryCreated events drive the embedding + graph pipelines above. Runs on
    # a background processor (drained on shutdown); offline default engine is
    # sequential (no LangGraph dependency).
    ingest_use_case = IngestMemoryUseCaseImpl(
        engine=build_workflow_engine(),
        uow_factory=lambda: SQLAlchemyUnitOfWork(postgres_manager.sessionmaker),
        dispatcher=in_process_dispatcher,
    )
    workflow_processor = InProcessWorkflowJobProcessor(ingest_use_case.process)
    app.state.workflow_processor = workflow_processor

    # --- Wire the write-time memory consolidation pipeline ---------------
    # Triggered by MemoryCreated; compares each new memory against the user's
    # recent corpus.  SUPERSEDES decisions archive the older memory; CONTRADICTS
    # decisions write a durable CONTRADICTS graph edge.  Offline default engine
    # is sequential (no LangGraph dependency).
    consolidation_config = ConsolidationConfig(
        candidate_pool=settings.consolidation_candidate_pool,
        contradict_confidence=settings.consolidation_contradict_confidence,
        supersede_confidence=settings.consolidation_supersede_confidence,
    )

    def _make_intelligence_service() -> MemoryIntelligenceService:
        return MemoryIntelligenceService(
            uow=SQLAlchemyUnitOfWork(postgres_manager.sessionmaker),
            dispatcher=in_process_dispatcher,
            config=IntelligenceConfig(),
        )

    consolidation_service = PersistentConsolidationService(
        uow_factory=lambda: SQLAlchemyUnitOfWork(postgres_manager.sessionmaker),
        engine=build_consolidation_engine(),
        intelligence_service_factory=_make_intelligence_service,
        graph_repo=build_graph_repository(),
        dispatcher=in_process_dispatcher,
        config=consolidation_config,
    )
    consolidation_processor = InProcessConsolidationJobProcessor(consolidation_service.process)
    ConsolidationEventHandler(consolidation_processor).register(in_process_dispatcher)
    app.state.consolidation_processor = consolidation_processor

    # --- Wire the Stage 11 maintenance workflows -------------------------
    # Event-driven relationship inference (MemoryCreated -> inference job) plus a
    # scheduler holding the decay/archival/promotion/summary jobs. The scheduler
    # runs no live ticker by default; a production driver fires jobs on their
    # crons. All reuse existing services and run off the request path.
    maintenance_processor = None
    scheduler = InProcessScheduler()
    if settings.maintenance_enabled:
        uow_factory = lambda: SQLAlchemyUnitOfWork(postgres_manager.sessionmaker)  # noqa: E731
        maintenance_config = MaintenanceConfig(
            inference_confidence_threshold=settings.inference_confidence_threshold,
            inference_candidate_pool=settings.inference_candidate_pool,
            summary_top_n=settings.summary_top_n,
            summary_max_chars=settings.summary_max_chars,
        )

        inference_service = RelationshipInferenceService(
            uow_factory=uow_factory,
            graph_repo=build_graph_repository(),
            config=maintenance_config,
            graph_config=graph_config,
        )
        maintenance_processor = InProcessMaintenanceJobProcessor(inference_service.process)
        InferenceEventHandler(maintenance_processor).register(in_process_dispatcher)
        app.state.maintenance_processor = maintenance_processor

        def _intelligence() -> MemoryIntelligenceService:
            return MemoryIntelligenceService(uow_factory(), in_process_dispatcher, IntelligenceConfig())

        summary_service = MemorySummaryService(
            uow_factory, DeterministicSummaryGenerator(), maintenance_config
        )
        scheduler.register(DecaySweepJob(uow_factory, _intelligence), cron=settings.decay_cron)
        scheduler.register(ArchivalSweepJob(uow_factory, _intelligence), cron=settings.archival_cron)
        scheduler.register(PromotionSweepJob(uow_factory, _intelligence), cron=settings.promotion_cron)
        scheduler.register(SummaryRefreshJob(uow_factory, summary_service), cron=settings.summary_cron)
        await scheduler.start()
    app.state.scheduler = scheduler
    _logger.info("startup.complete")

    try:
        yield
    finally:
        # --- Shutdown: drain background work, then release resources ------
        _logger.info("shutdown.begin")
        await embedding_processor.drain()
        await graph_processor.drain()
        await workflow_processor.drain()
        await consolidation_processor.drain()
        if maintenance_processor is not None:
            await maintenance_processor.drain()
        await scheduler.stop()
        await neo4j_manager.disconnect()
        await redis_manager.disconnect()
        await postgres_manager.disconnect()
        _logger.info("shutdown.complete")


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    # Stash settings on app.state so the lifespan and overrides can reach them.
    app.state.settings = settings

    # Middleware (outermost first): CORS, then request-context logging.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextLogMiddleware)

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.api_v1_prefix)

    return app


# ASGI entrypoint: `uvicorn app.main:app`
app = create_app()
