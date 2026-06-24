"""Knowledge-graph API endpoints (API v1).

* ``/graph/search``      — graph-aware retrieval (hybrid + graph expansion).
* ``/graph/traverse``    — depth-limited traversal from a node.
* ``/graph/memory/{id}`` — a memory's node plus its immediate neighbors/edges.
* ``/graph/debug``       — graph-aware retrieval with hybrid/graph counts exposed.

No LLM, no agents — graph memory only.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter

from fastapi import Depends

from app.api.v1.dependencies.providers import (
    CurrentPrincipalDep,
    GraphAwareRetrievalServiceDep,
    GraphRepositoryDep,
    GraphTraversalServiceDep,
    get_app_settings,
)
from app.application.dto.auth_dto import AuthPrincipal
from app.core.config import Settings
from app.application.interfaces.graph_repository import GraphRepository
from app.application.services.authorization import authorize_owner
from app.application.exceptions import ResourceNotFoundForCaller
from app.application.services.graph.graph_aware_retrieval import GraphAwareRetrievalService
from app.application.services.graph.traversal_service import GraphTraversalService
from app.core.logging import get_request_id
from app.schemas.graph import (
    GraphAwareResultSchema,
    GraphEdgeSchema,
    GraphMemoryViewSchema,
    GraphNodeSchema,
    GraphOverviewSchema,
    GraphSearchRequestSchema,
    GraphTraversalResultSchema,
    GraphTraverseRequestSchema,
)
from app.schemas.responses import APIResponse

router = APIRouter(prefix="/graph", tags=["graph"])


def _node_owner(node) -> UUID:  # type: ignore[no-untyped-def]
    """Parse a graph node's owner user_id (404 to callers if absent/invalid)."""
    try:
        return UUID(str(node.properties.get("user_id")))
    except (TypeError, ValueError):
        raise ResourceNotFoundForCaller() from None


@router.post(
    "/search",
    response_model=APIResponse[GraphAwareResultSchema],
    summary="Graph-aware retrieval: hybrid results expanded via the graph",
)
async def graph_search(
    payload: GraphSearchRequestSchema,
    service: GraphAwareRetrievalService = GraphAwareRetrievalServiceDep,
) -> APIResponse[GraphAwareResultSchema]:
    result = await service.search(payload.to_query(), expand_depth=payload.expand_depth)
    return APIResponse(data=GraphAwareResultSchema.from_dto(result), request_id=get_request_id())


@router.post(
    "/traverse",
    response_model=APIResponse[GraphTraversalResultSchema],
    summary="Depth-limited traversal from a node",
)
async def graph_traverse(
    payload: GraphTraverseRequestSchema,
    service: GraphTraversalService = GraphTraversalServiceDep,
) -> APIResponse[GraphTraversalResultSchema]:
    result = await service.traverse(payload.node_id, depth=payload.depth)
    return APIResponse(data=GraphTraversalResultSchema.from_dto(result), request_id=get_request_id())


@router.get(
    "/memory/{memory_id}",
    response_model=APIResponse[GraphMemoryViewSchema],
    summary="A memory's graph node with its immediate neighbors and edges",
)
async def graph_memory(
    memory_id: UUID,
    repository: GraphRepository = GraphRepositoryDep,
    principal: AuthPrincipal | None = CurrentPrincipalDep,
) -> APIResponse[GraphMemoryViewSchema]:
    node_id = str(memory_id)
    node = await repository.get_node(node_id)
    # Ownership: a caller may only view their own memory's graph node (404 to
    # others). No-op when auth is disabled.
    if principal is not None:
        if node is None:
            raise ResourceNotFoundForCaller()
        authorize_owner(principal, _node_owner(node))
    neighbors = await repository.find_neighbors(node_id, depth=1)
    edges = await repository.get_edges(node_id)
    view = GraphMemoryViewSchema(
        node=GraphNodeSchema.from_dto(node) if node else None,
        neighbors=[GraphNodeSchema.from_dto(n) for n in neighbors],
        edges=[GraphEdgeSchema.from_dto(e) for e in edges],
    )
    return APIResponse(data=view, request_id=get_request_id())


@router.get(
    "/overview/{user_id}",
    response_model=APIResponse[GraphOverviewSchema],
    summary="A tenant's full graph (nodes + RELATED_TO/CONTRADICTS/SUPERSEDES edges)",
)
async def graph_overview(
    user_id: UUID,
    repository: GraphRepository = GraphRepositoryDep,
    principal: AuthPrincipal | None = CurrentPrincipalDep,
    settings: Settings = Depends(get_app_settings),
) -> APIResponse[GraphOverviewSchema]:
    # A caller may only view their own graph (no-op when auth is disabled).
    if principal is not None:
        authorize_owner(principal, user_id)
    # Large-graph protection: cap the overview payload (maintenance is uncapped).
    overview = await repository.get_subgraph(user_id, limit=settings.graph_overview_max_nodes)
    return APIResponse(
        data=GraphOverviewSchema.from_dto(user_id, overview), request_id=get_request_id()
    )


@router.post(
    "/debug",
    response_model=APIResponse[GraphAwareResultSchema],
    summary="Graph-aware retrieval with hybrid/graph provenance counts",
)
async def graph_debug(
    payload: GraphSearchRequestSchema,
    service: GraphAwareRetrievalService = GraphAwareRetrievalServiceDep,
) -> APIResponse[GraphAwareResultSchema]:
    result = await service.search(payload.to_query(), expand_depth=payload.expand_depth)
    return APIResponse(data=GraphAwareResultSchema.from_dto(result), request_id=get_request_id())
