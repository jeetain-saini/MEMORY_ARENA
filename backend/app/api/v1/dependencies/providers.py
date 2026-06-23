"""FastAPI dependency providers (the read side of the composition root).

These thin functions expose the process-wide singletons to route handlers via
`Depends(...)`. Handlers ask for *what they need* (a session, the cache client)
without knowing how it was constructed — keeping the dependency rule intact and
making handlers trivially testable by overriding the provider in tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from neo4j import AsyncDriver
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.interfaces.agent_runtime import AgentRuntime
from app.application.interfaces.cache_provider import CacheProvider
from app.application.interfaces.clock import Clock
from app.application.interfaces.context_compressor import ContextCompressor
from app.application.interfaces.metrics_sink import MetricsSink
from app.application.interfaces.password_hasher import PasswordHasher
from app.application.interfaces.principal_provider import PrincipalProvider
from app.application.interfaces.refresh_token_store import RefreshTokenStore
from app.application.interfaces.token_service import TokenService
from app.application.dto.auth_dto import AuthPrincipal
from app.application.interfaces.embedding_provider import EmbeddingProvider
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.reranker import Reranker
from app.application.interfaces.trace_recorder import TraceRecorder
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.interfaces.consolidation_job_processor import ConsolidationJobProcessor
from app.application.interfaces.workflow_job_processor import WorkflowJobProcessor
from app.application.dto.agent_dto import AgentConfig
from app.application.services.agent.conversation_capture_policy import (
    ConversationCapturePolicy,
)
from app.application.services.agent.conversation_capture_service import (
    ConversationCaptureService,
)
from app.application.services.agent.tools import (
    ContextBuilderTool,
    GraphExpansionTool,
    MemorySearchTool,
)
from app.application.services.agent.toolset import AgentToolSet
from app.application.services.graph.config import GraphConfig
from app.application.services.maintenance.config import MaintenanceConfig
from app.application.services.maintenance.memory_summary_service import MemorySummaryService
from app.application.services.graph.graph_aware_retrieval import GraphAwareRetrievalService
from app.application.services.graph.traversal_service import GraphTraversalService
from app.application.services.context.config import ContextConfig
from app.application.services.context.conflict_detector import ConflictDetector
from app.application.services.context.consolidation_service import MemoryConsolidationService
from app.application.services.context.context_builder import ContextBuilderService
from app.application.services.context.selection_service import MemorySelectionService
from app.application.services.context.tokenization import HeuristicTokenCounter
from app.application.services.retrieval.config import RetrievalConfig
from app.application.services.retrieval.hybrid_retriever import HybridRetriever
from app.application.services.retrieval.keyword_retriever import KeywordRetriever
from app.application.services.retrieval.reranker import SimpleCrossEncoderReranker
from app.application.services.intelligence.clustering_engine import ClusteringEngine
from app.application.services.intelligence.forgetting_engine import ForgettingEngine
from app.application.services.intelligence.promotion_engine import PromotionEngine
from app.application.services.intelligence.evolving_retrieval_tracker import (
    EvolvingRetrievalTracker,
)
from app.application.services.retrieval.retrieval_service import MemoryRetrievalService
from app.application.services.retrieval.vector_retriever import VectorRetriever
from app.application.services.decay_strategies import DecayStrategy, ExponentialDecayStrategy
from app.application.services.intelligence_config import IntelligenceConfig
from app.application.services.memory_analytics_service import MemoryAnalyticsService
from app.application.services.contradiction_resolution_service import (
    ContradictionResolutionService,
)
from app.application.services.memory_intelligence_service import MemoryIntelligenceService
from app.application.services.observability.memory_health_service import MemoryHealthService
from app.application.services.auth.auth_service import AuthService
from app.application.services.memory_service import MemoryService
from app.application.use_cases.query_memory_use_cases import QueryMemoryUseCase
from app.application.use_cases.query_memory_use_cases_impl import QueryMemoryUseCaseImpl
from app.core.config import Settings, get_settings
from app.core.exceptions import AppException
from app.infrastructure.auth.factory import (
    build_password_hasher,
    build_refresh_token_store,
    build_token_service,
)
from app.infrastructure.cache.factory import build_cache_provider
from app.infrastructure.cache.redis import redis_manager
from app.infrastructure.database.postgres import postgres_manager
from app.infrastructure.database.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.embeddings.factory import build_embedding_provider
from app.infrastructure.events.in_process_dispatcher import in_process_dispatcher
from app.infrastructure.llm.compressors.factory import build_context_compressor
from app.infrastructure.graph.factory import build_graph_repository
from app.infrastructure.graph.neo4j import neo4j_manager
from app.infrastructure.llm.graphs.factory import build_agent_runtime
from app.infrastructure.llm.providers.factory import build_llm_provider
from app.infrastructure.observability.factory import build_trace_recorder
from app.infrastructure.observability.metrics_factory import build_metrics_sink
from app.infrastructure.observability.monotonic_clock import MonotonicClock
from app.infrastructure.vector.factory import build_vector_index
from app.infrastructure.security.jwt_principal_provider import JwtPrincipalProvider
from app.infrastructure.summaries.deterministic_summary_generator import (
    DeterministicSummaryGenerator,
)


def get_app_settings() -> Settings:
    """Provide the cached application settings."""
    return get_settings()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Provide a transactional async SQLAlchemy session, closed after the request."""
    async with postgres_manager.sessionmaker() as session:
        yield session


def get_redis() -> Redis:
    """Provide the shared async Redis client."""
    return redis_manager.client


def get_neo4j() -> AsyncDriver:
    """Provide the shared async Neo4j driver."""
    return neo4j_manager.driver


def get_unit_of_work() -> UnitOfWork:
    """Provide a fresh Unit of Work bound to the shared session factory.

    The composition root supplies the SQLAlchemy implementation behind the
    ``UnitOfWork`` abstraction the use cases depend on.
    """
    return SQLAlchemyUnitOfWork(postgres_manager.sessionmaker)


def get_event_dispatcher() -> EventDispatcher:
    """Provide the process-wide in-process event dispatcher (singleton)."""
    return in_process_dispatcher


def get_embedding_provider() -> EmbeddingProvider:
    """Provide the configured embedding provider (process-wide singleton)."""
    return build_embedding_provider()


def get_metrics_sink() -> MetricsSink:
    """Provide the configured metrics sink (process-wide singleton, Stage 14)."""
    return build_metrics_sink()


def get_cache_provider() -> CacheProvider:
    """Provide the configured cache provider (process-wide singleton, Stage 14).

    Defaults to NoOp (cache-aside becomes a pass-through). Shared with the
    invalidation event handler so the in-memory backend invalidates the same store.
    """
    return build_cache_provider()


# --- Clock + authenticated principal (Stage 13/14) --------------------------
# Defined early so the resource-service providers below can depend on the
# current principal.
_bearer_scheme = HTTPBearer(auto_error=False)


def get_clock() -> Clock:
    """Provide the monotonic+wall clock (stage timing + token expiry)."""
    return MonotonicClock()


def get_principal_provider(clock: Clock = Depends(get_clock)) -> PrincipalProvider:
    """Provide the PrincipalProvider (JWT-backed adapter behind the port).

    Composition only: the JWT/decoding specifics live in the adapter, so the rest
    of the composition root and the services depend on the port abstraction.
    """
    def uow_factory() -> UnitOfWork:
        return SQLAlchemyUnitOfWork(postgres_manager.sessionmaker)

    return JwtPrincipalProvider(build_token_service(clock), uow_factory)


async def get_current_principal(
    settings: Settings = Depends(get_app_settings),
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    provider: PrincipalProvider = Depends(get_principal_provider),
) -> AuthPrincipal | None:
    """Resolve the request's principal, or None when auth is disabled.

    The AUTH_ENABLED feature gate lives here; token decoding / user loading /
    active-user verification are delegated to the PrincipalProvider port.
    """
    if not settings.auth_enabled:
        return None
    token = credentials.credentials if credentials is not None else None
    return await provider.get_principal(token)


def get_memory_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
    dispatcher: EventDispatcher = Depends(get_event_dispatcher),
    principal: AuthPrincipal | None = Depends(get_current_principal),
) -> MemoryService:
    """Assemble the MemoryService for a request from its dependencies."""
    return MemoryService(uow, dispatcher, principal)


def get_intelligence_config() -> IntelligenceConfig:
    """Provide the (tunable) intelligence thresholds. Defaults for now."""
    return IntelligenceConfig()


def get_decay_strategy() -> DecayStrategy:
    """Provide the configured recency-decay strategy (default: exponential)."""
    return ExponentialDecayStrategy()


def get_memory_intelligence_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
    dispatcher: EventDispatcher = Depends(get_event_dispatcher),
    config: IntelligenceConfig = Depends(get_intelligence_config),
    decay_strategy: DecayStrategy = Depends(get_decay_strategy),
    principal: AuthPrincipal | None = Depends(get_current_principal),
) -> MemoryIntelligenceService:
    """Assemble the Memory Intelligence Engine for a request."""
    return MemoryIntelligenceService(uow, dispatcher, config, decay_strategy, principal)


def get_memory_analytics_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
    principal: AuthPrincipal | None = Depends(get_current_principal),
    cache: CacheProvider = Depends(get_cache_provider),
    metrics: MetricsSink = Depends(get_metrics_sink),
    settings: Settings = Depends(get_app_settings),
) -> MemoryAnalyticsService:
    """Assemble the analytics service for a request (cache-aside + metrics)."""
    return MemoryAnalyticsService(
        uow, principal, cache, metrics, cache_ttl_seconds=settings.cache_ttl_seconds
    )


def get_retrieval_config() -> RetrievalConfig:
    """Provide the (tunable) hybrid-retrieval weights. Defaults for now."""
    return RetrievalConfig()


def get_reranker(
    config: RetrievalConfig = Depends(get_retrieval_config),
) -> Reranker:
    """Provide the reranker (heuristic cross-encoder for now)."""
    return SimpleCrossEncoderReranker(overlap_weight=config.rerank_overlap_weight)


def get_memory_retrieval_service(
    provider: EmbeddingProvider = Depends(get_embedding_provider),
    config: RetrievalConfig = Depends(get_retrieval_config),
    reranker: Reranker = Depends(get_reranker),
    principal: AuthPrincipal | None = Depends(get_current_principal),
    metrics: MetricsSink = Depends(get_metrics_sink),
    clock: Clock = Depends(get_clock),
) -> MemoryRetrievalService:
    """Assemble the hybrid retrieval pipeline for a request.

    Retrievers receive a Unit-of-Work *factory* (not a shared instance) so the
    vector and keyword stages can run concurrently, each on its own session. The
    vector index is selected by ``VECTOR_SEARCH_MODE`` (scan default).
    """
    def uow_factory() -> UnitOfWork:
        return SQLAlchemyUnitOfWork(postgres_manager.sessionmaker)

    vector = VectorRetriever(
        uow_factory, provider, index=build_vector_index(uow_factory), metrics=metrics, clock=clock
    )
    keyword = KeywordRetriever(uow_factory, config)
    hybrid = HybridRetriever(vector, keyword, config)
    # Stage 17.1: record retrieval frequency *and* evolve importance from it.
    tracker = EvolvingRetrievalTracker(uow_factory)
    return MemoryRetrievalService(hybrid, reranker, principal, metrics, clock, tracker)


def get_graph_config() -> GraphConfig:
    """Provide the (tunable) knowledge-graph configuration."""
    return GraphConfig()


def get_graph_repository() -> GraphRepository:
    """Provide the configured graph repository (process-wide singleton)."""
    return build_graph_repository()


def get_contradiction_resolution_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
    graph_repo: GraphRepository = Depends(get_graph_repository),
    dispatcher: EventDispatcher = Depends(get_event_dispatcher),
    principal: AuthPrincipal | None = Depends(get_current_principal),
) -> ContradictionResolutionService:
    """Assemble the contradiction-resolution service for a request (Stage 16)."""
    return ContradictionResolutionService(uow, graph_repo, dispatcher, principal)


def _intelligence_uow_factory() -> UnitOfWork:
    return SQLAlchemyUnitOfWork(postgres_manager.sessionmaker)


def get_promotion_engine(
    graph_repo: GraphRepository = Depends(get_graph_repository),
    dispatcher: EventDispatcher = Depends(get_event_dispatcher),
) -> PromotionEngine:
    """Assemble the episodic->semantic promotion engine (Stage 17)."""
    return PromotionEngine(_intelligence_uow_factory, graph_repo, dispatcher)


def get_forgetting_engine(
    graph_repo: GraphRepository = Depends(get_graph_repository),
    dispatcher: EventDispatcher = Depends(get_event_dispatcher),
) -> ForgettingEngine:
    """Assemble the forgetting engine (Stage 17)."""
    return ForgettingEngine(_intelligence_uow_factory, graph_repo, dispatcher)


def get_clustering_engine(
    graph_repo: GraphRepository = Depends(get_graph_repository),
) -> ClusteringEngine:
    """Assemble the semantic clustering engine (Stage 17)."""
    return ClusteringEngine(_intelligence_uow_factory, graph_repo)


def get_graph_traversal_service(
    repository: GraphRepository = Depends(get_graph_repository),
    config: GraphConfig = Depends(get_graph_config),
    principal: AuthPrincipal | None = Depends(get_current_principal),
) -> GraphTraversalService:
    return GraphTraversalService(repository, config, principal)


def get_memory_health_service(
    uow: UnitOfWork = Depends(get_unit_of_work),
    graph_repository: GraphRepository = Depends(get_graph_repository),
    principal: AuthPrincipal | None = Depends(get_current_principal),
    cache: CacheProvider = Depends(get_cache_provider),
    metrics: MetricsSink = Depends(get_metrics_sink),
    settings: Settings = Depends(get_app_settings),
) -> MemoryHealthService:
    """Assemble the memory-health metrics service for a request (cache-aside + metrics)."""
    return MemoryHealthService(
        uow, graph_repository, principal, cache, metrics, cache_ttl_seconds=settings.cache_ttl_seconds
    )


def get_graph_aware_retrieval_service(
    retrieval_service: MemoryRetrievalService = Depends(get_memory_retrieval_service),
    repository: GraphRepository = Depends(get_graph_repository),
    config: GraphConfig = Depends(get_graph_config),
    principal: AuthPrincipal | None = Depends(get_current_principal),
) -> GraphAwareRetrievalService:
    return GraphAwareRetrievalService(retrieval_service, repository, config, principal)


def get_workflow_processor(request: Request) -> WorkflowJobProcessor:
    """Provide the workflow job processor wired in the app lifespan.

    Read from ``app.state`` (set on startup) so the ingest endpoint can submit
    jobs without constructing the background machinery itself. Overridable in
    tests via the standard dependency-override mechanism.
    """
    return request.app.state.workflow_processor


def get_consolidation_processor(request: Request) -> ConsolidationJobProcessor:
    """Provide the consolidation job processor wired in the app lifespan."""
    return request.app.state.consolidation_processor


def get_context_config() -> ContextConfig:
    """Provide the (tunable) context-assembly configuration."""
    return ContextConfig()


def get_context_compressor() -> ContextCompressor:
    """Provide the configured context compressor (process-wide singleton).

    Defaults to the heuristic compressor; ``CONTEXT_COMPRESSOR=llm`` selects the
    LLM compressor (which itself falls back to the heuristic on any failure).
    """
    return build_context_compressor()


def get_context_builder_service(
    retrieval_service: MemoryRetrievalService = Depends(get_memory_retrieval_service),
    config: ContextConfig = Depends(get_context_config),
    compressor: ContextCompressor = Depends(get_context_compressor),
    principal: AuthPrincipal | None = Depends(get_current_principal),
) -> ContextBuilderService:
    """Assemble the Context Assembly pipeline for a request."""
    token_counter = HeuristicTokenCounter()
    return ContextBuilderService(
        retrieval_service=retrieval_service,
        selection_service=MemorySelectionService(token_counter),
        consolidation_service=MemoryConsolidationService(config.dedup_threshold),
        conflict_detector=ConflictDetector(config.conflict_threshold),
        compressor=compressor,
        principal=principal,
    )


def get_agent_config(settings: Settings = Depends(get_app_settings)) -> AgentConfig:
    """Build the agent guardrail/budget config from settings."""
    return AgentConfig(
        max_tokens=settings.agent_max_tokens,
        answer_max_tokens=settings.agent_answer_max_tokens,
        max_iterations=settings.agent_max_iterations,
        max_tool_calls=settings.agent_max_tool_calls,
        max_citations=settings.agent_max_citations,
        timeout_seconds=settings.agent_timeout_seconds,
        top_k=settings.agent_top_k,
    )


def get_agent_runtime(
    retrieval_service: MemoryRetrievalService = Depends(get_memory_retrieval_service),
    graph_aware: GraphAwareRetrievalService = Depends(get_graph_aware_retrieval_service),
    context_builder: ContextBuilderService = Depends(get_context_builder_service),
    clock: Clock = Depends(get_clock),
) -> AgentRuntime:
    """Assemble the query-time agent runtime for a request.

    The tool set wraps the existing services; the runtime (sequential default or
    LangGraph) is selected by configuration. Retrieval runs once — the graph tool
    reuses the base hits via ``expand`` and the builder consumes the combined set.
    """
    toolset = AgentToolSet(
        MemorySearchTool(retrieval_service),
        GraphExpansionTool(graph_aware),
        ContextBuilderTool(context_builder),
    )
    return build_agent_runtime(toolset, build_llm_provider(), HeuristicTokenCounter(), clock)


def get_trace_recorder() -> TraceRecorder:
    """Provide the configured trace recorder (process-wide singleton, Stage 13).

    Defaults to the in-memory ring buffer; ``TRACE_RECORDER=noop`` disables it and
    ``LANGSMITH_ENABLED=true`` selects the (lazy) LangSmith exporter.
    """
    return build_trace_recorder()


def get_query_use_case(
    runtime: AgentRuntime = Depends(get_agent_runtime),
    recorder: TraceRecorder = Depends(get_trace_recorder),
    principal: AuthPrincipal | None = Depends(get_current_principal),
    processor: WorkflowJobProcessor = Depends(get_workflow_processor),
    settings: Settings = Depends(get_settings),
) -> QueryMemoryUseCase:
    """Assemble the query use case for a request.

    Conversational capture (Stage 15) reuses the ingestion processor; it is a
    no-op unless ``CONVERSATION_CAPTURE_ENABLED`` is set.
    """
    capture = ConversationCaptureService(
        processor,
        ConversationCapturePolicy(min_tokens=settings.capture_min_tokens),
        enabled=settings.conversation_capture_enabled,
    )
    return QueryMemoryUseCaseImpl(runtime, recorder, principal, capture)


def get_summary_service(
    principal: AuthPrincipal | None = Depends(get_current_principal),
) -> MemorySummaryService:
    """Assemble the summary service for a request (read endpoints).

    Mirrors ``get_memory_service``: reads go through the service, which delegates
    to ``MemorySummaryRepository`` within a fresh Unit of Work. The deterministic
    generator is supplied to satisfy the constructor; the read paths do not use it.
    """
    def uow_factory() -> UnitOfWork:
        return SQLAlchemyUnitOfWork(postgres_manager.sessionmaker)

    return MemorySummaryService(
        uow_factory, DeterministicSummaryGenerator(), MaintenanceConfig(), principal
    )


# --- Authentication (Stage 14 Phase 2) --------------------------------------
def require_auth_enabled(settings: Settings = Depends(get_app_settings)) -> None:
    """Gate the /auth router: 404 when AUTH_ENABLED is false (feature hidden)."""
    if not settings.auth_enabled:
        raise AppException(
            "Not found", error_code="not_found", status_code=404
        )


def get_password_hasher() -> PasswordHasher:
    """Provide the configured password hasher (process-wide singleton)."""
    return build_password_hasher()


def get_token_service(clock: Clock = Depends(get_clock)) -> TokenService:
    """Provide the access-token service (clock-driven expiry)."""
    return build_token_service(clock)


def get_refresh_token_store(clock: Clock = Depends(get_clock)) -> RefreshTokenStore:
    """Provide the refresh-token store (NoOp when auth disabled, else Redis)."""
    return build_refresh_token_store(clock)


def get_auth_service(
    settings: Settings = Depends(get_app_settings),
    hasher: PasswordHasher = Depends(get_password_hasher),
    token_service: TokenService = Depends(get_token_service),
    refresh_store: RefreshTokenStore = Depends(get_refresh_token_store),
    clock: Clock = Depends(get_clock),
) -> AuthService:
    """Assemble the AuthService for a request from its collaborators."""
    def uow_factory() -> UnitOfWork:
        return SQLAlchemyUnitOfWork(postgres_manager.sessionmaker)

    return AuthService(
        uow_factory,
        hasher,
        token_service,
        refresh_store,
        clock,
        refresh_ttl_seconds=settings.refresh_token_expire_days * 86400,
    )


# Convenience aliases for annotated dependencies.
SettingsDep = Depends(get_app_settings)
DBSessionDep = Depends(get_db_session)
RedisDep = Depends(get_redis)
Neo4jDep = Depends(get_neo4j)
UnitOfWorkDep = Depends(get_unit_of_work)
EventDispatcherDep = Depends(get_event_dispatcher)
MemoryServiceDep = Depends(get_memory_service)
MemoryIntelligenceServiceDep = Depends(get_memory_intelligence_service)
ContradictionResolutionServiceDep = Depends(get_contradiction_resolution_service)
MemoryAnalyticsServiceDep = Depends(get_memory_analytics_service)
MemoryHealthServiceDep = Depends(get_memory_health_service)
EmbeddingProviderDep = Depends(get_embedding_provider)
MemoryRetrievalServiceDep = Depends(get_memory_retrieval_service)
ContextBuilderServiceDep = Depends(get_context_builder_service)
GraphRepositoryDep = Depends(get_graph_repository)
GraphTraversalServiceDep = Depends(get_graph_traversal_service)
GraphAwareRetrievalServiceDep = Depends(get_graph_aware_retrieval_service)
WorkflowProcessorDep = Depends(get_workflow_processor)
AgentConfigDep = Depends(get_agent_config)
AgentRuntimeDep = Depends(get_agent_runtime)
QueryUseCaseDep = Depends(get_query_use_case)
SummaryServiceDep = Depends(get_summary_service)
TraceRecorderDep = Depends(get_trace_recorder)
MetricsSinkDep = Depends(get_metrics_sink)
AuthServiceDep = Depends(get_auth_service)
CurrentPrincipalDep = Depends(get_current_principal)
