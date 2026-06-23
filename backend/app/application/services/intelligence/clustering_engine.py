"""ClusteringEngine — deterministic semantic clustering (Stage 17 Area 7).

Groups a user's memories into clusters by shared significant terms (connected
components over token overlap) — no LLM required. Each cluster gets a stable id
(hash of sorted member ids), a name (top shared tokens), a score (mean pairwise
overlap), and a size. Members are linked in the graph by ``CLUSTER_MEMBER`` edges
(star topology from a representative), and each member is stamped with its
cluster id in metadata so retrieval can use a cluster-relevance signal.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.metrics_sink import MetricsSink
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.context._text import jaccard
from app.application.services.context.conflict_detector import STOPWORDS
from app.application.services.retrieval.bm25 import tokenize
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_status import MemoryStatus

_logger = logging.getLogger("memoryarena.clustering")
_CLUSTER_KEY = "cluster_id"


@dataclass(frozen=True)
class ClusterConfig:
    min_overlap: float = 0.2   # token Jaccard to link two memories
    min_size: int = 2          # smallest reported cluster


@dataclass(frozen=True)
class ClusterSummary:
    cluster_id: str
    name: str
    score: float
    size: int
    member_ids: list[UUID]


def _sig(content: str) -> set[str]:
    return {t for t in tokenize(content) if t not in STOPWORDS and len(t) > 2}


class ClusteringEngine:
    def __init__(
        self, uow_factory: Callable[[], UnitOfWork], graph_repo: GraphRepository,
        config: ClusterConfig | None = None,
        *,
        metrics: MetricsSink | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._graph = graph_repo
        self._config = config or ClusterConfig()
        self._metrics = metrics

    async def cluster_user(self, user_id: UUID) -> list[ClusterSummary]:
        async with self._uow_factory() as uow:
            memories = [
                m for m in await uow.memories.list_for_analytics(user_id)
                if m.status is MemoryStatus.ACTIVE
            ]
        sigs = {m.id: _sig(m.content) for m in memories}
        components = self._connected_components(memories, sigs)

        summaries: list[ClusterSummary] = []
        for comp in components:
            if len(comp) < self._config.min_size:
                continue
            summaries.append(await self._materialize(comp, sigs))
        _logger.info("clustering.done", extra={"clusters": len(summaries)})
        return summaries

    def _connected_components(
        self, memories: list[Memory], sigs: dict[UUID, set[str]]
    ) -> list[list[Memory]]:
        parent: dict[UUID, UUID] = {m.id: m.id for m in memories}

        def find(x: UUID) -> UUID:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: UUID, b: UUID) -> None:
            parent[find(a)] = find(b)

        for i, a in enumerate(memories):
            for b in memories[i + 1 :]:
                if sigs[a.id] and sigs[b.id] and jaccard(sigs[a.id], sigs[b.id]) >= self._config.min_overlap:
                    union(a.id, b.id)

        groups: dict[UUID, list[Memory]] = {}
        for m in memories:
            groups.setdefault(find(m.id), []).append(m)
        return list(groups.values())

    async def _materialize(
        self, members: list[Memory], sigs: dict[UUID, set[str]]
    ) -> ClusterSummary:
        ordered = sorted(members, key=lambda m: str(m.id))
        ids = [m.id for m in ordered]
        cluster_id = hashlib.sha1("".join(str(i) for i in ids).encode()).hexdigest()[:12]
        shared = set.intersection(*(sigs[i] for i in ids)) if all(sigs[i] for i in ids) else set()
        all_tokens = sorted({t for i in ids for t in sigs[i]})
        name = " / ".join(sorted(shared)[:3]) or " / ".join(all_tokens[:3]) or "cluster"
        # cluster score = mean pairwise token overlap.
        pairs = [
            jaccard(sigs[a], sigs[b])
            for k, a in enumerate(ids) for b in ids[k + 1 :]
        ]
        score = round(sum(pairs) / len(pairs), 4) if pairs else 0.0

        rep = ordered[0]
        id_strs = {str(i) for i in ids}
        # Phase 2: only write members whose cluster_id actually changed. A stable
        # cluster re-run produces zero PostgreSQL writes.
        async with self._uow_factory() as uow:
            for m in ordered:
                if m.metadata.get(_CLUSTER_KEY) == cluster_id:
                    continue
                m.metadata[_CLUSTER_KEY] = cluster_id
                await uow.memories.update(m)
                if self._metrics is not None:
                    self._metrics.incr("clustering.member_writes_total")
            await uow.commit()

        # Phase 4: prune stale CLUSTER_MEMBER edges on the representative before
        # (re)creating the current star, so the graph reflects current state and
        # edge count stabilizes. Other edge types (PROMOTED_FROM / CONTRADICTS /
        # SUPERSEDES) are explicitly preserved.
        for edge in await self._graph.get_edges(str(rep.id)):
            if edge.edge_type is not GraphEdgeType.CLUSTER_MEMBER:
                continue
            other = edge.target_id if edge.source_id == str(rep.id) else edge.source_id
            if other not in id_strs:
                await self._graph.delete_edge(
                    edge.source_id, edge.target_id, GraphEdgeType.CLUSTER_MEMBER
                )
                if self._metrics is not None:
                    self._metrics.incr("clustering.stale_edges_removed_total")
        for m in ordered[1:]:
            await self._graph.create_edge(
                GraphEdge(
                    source_id=str(rep.id), target_id=str(m.id),
                    edge_type=GraphEdgeType.CLUSTER_MEMBER, weight=score,
                    properties={"cluster_id": cluster_id, "cluster_name": name, "cluster_size": len(ids)},
                )
            )
        return ClusterSummary(
            cluster_id=cluster_id, name=name, score=score, size=len(ids), member_ids=ids
        )
