"""GraphAwareRetrievalService — hybrid retrieval enriched by graph expansion.

    Query -> Hybrid Retrieval -> Graph Expansion -> Expanded Result Set

Direct hits keep their retrieval score and provenance ``hybrid``. Each hit's
graph neighbors are pulled in, tagged provenance ``graph`` (with the seed they
came from) and scored at a decayed fraction of the seed's score, so expanded
memories surface useful context without outranking direct matches.
"""

from __future__ import annotations

from uuid import UUID

from app.application.dto.auth_dto import AuthPrincipal
from app.application.dto.graph_dto import ExpandedMemory, GraphAwareResult
from app.application.dto.retrieval_dto import MemorySearchQuery, RetrievalResult
from app.application.interfaces.graph_repository import GraphRepository
from app.application.services.authorization import resolve_scope
from app.application.services.graph.config import GraphConfig
from app.application.services.retrieval.retrieval_service import MemoryRetrievalService
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType


class GraphAwareRetrievalService:
    def __init__(
        self,
        retrieval_service: MemoryRetrievalService,
        repository: GraphRepository,
        config: GraphConfig | None = None,
        principal: AuthPrincipal | None = None,
    ) -> None:
        self._retrieval = retrieval_service
        self._repo = repository
        self._config = config or GraphConfig()
        self._principal = principal

    async def search(
        self, query: MemorySearchQuery, *, expand_depth: int | None = None
    ) -> GraphAwareResult:
        base = await self._retrieval.search(query)
        return await self.expand(base, query, expand_depth=expand_depth)

    async def expand(
        self,
        base: RetrievalResult,
        query: MemorySearchQuery,
        *,
        expand_depth: int | None = None,
    ) -> GraphAwareResult:
        """Expand an already-retrieved result set along graph edges.

        Separated from ``search`` so a caller (e.g. the agent runtime) that has
        already run hybrid retrieval can reuse those hits instead of retrieving a
        second time. ``search`` simply retrieves then delegates here.
        """
        resolve_scope(self._principal, query.user_id)
        depth = expand_depth or self._config.expansion_depth

        results: list[ExpandedMemory] = []
        seen: set[UUID] = set()
        for hit in base.results:
            seen.add(hit.memory_id)
            results.append(
                ExpandedMemory(
                    memory_id=hit.memory_id,
                    content=hit.content,
                    memory_type=hit.memory_type,
                    status=hit.status,
                    score=hit.final_score,
                    provenance="hybrid",
                )
            )

        hybrid_count = len(results)
        graph_count = 0
        edge_types = list(self._config.expansion_edge_types)
        query_statuses = query.filters.statuses
        allowed_statuses = set(query_statuses) if query_statuses else {MemoryStatus.ACTIVE}
        for hit in base.results:
            neighbors = await self._repo.find_neighbors(
                str(hit.memory_id), depth=depth, edge_types=edge_types
            )
            for node in neighbors[: self._config.max_neighbors]:
                expanded = self._node_to_expanded(
                    node,
                    seed_score=hit.final_score,
                    seed_id=hit.memory_id,
                    user_id=query.user_id,
                    allowed_statuses=allowed_statuses,
                )
                if expanded is None or expanded.memory_id in seen:
                    continue
                seen.add(expanded.memory_id)
                results.append(expanded)
                graph_count += 1

        results.sort(key=lambda m: m.score, reverse=True)
        return GraphAwareResult(
            query=query.query,
            user_id=query.user_id,
            results=results,
            hybrid_count=hybrid_count,
            graph_count=graph_count,
        )

    def _node_to_expanded(
        self,
        node,
        *,
        seed_score: float,
        seed_id: UUID,
        user_id: UUID,
        allowed_statuses: set[MemoryStatus],
    ) -> ExpandedMemory | None:
        props = node.properties
        try:
            memory_id = UUID(node.node_id)
        except ValueError:
            return None
        # Tenant isolation: never expand a neighbor belonging to another user.
        if str(props.get("user_id", "")) != str(user_id):
            return None
        status = MemoryStatus(props.get("status", MemoryStatus.ACTIVE.value))
        if status not in allowed_statuses:
            return None
        return ExpandedMemory(
            memory_id=memory_id,
            content=str(props.get("content", node.label)),
            memory_type=MemoryType(props.get("memory_type", MemoryType.FACT.value)),
            status=status,
            score=round(seed_score * self._config.graph_score_decay, 6),
            provenance="graph",
            source_memory_id=seed_id,
        )
