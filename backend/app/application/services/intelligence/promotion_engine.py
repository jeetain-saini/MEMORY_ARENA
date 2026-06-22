"""PromotionEngine — episodic -> semantic promotion (Stage 17 Area 5).

When the same episodic memory recurs (e.g. "I am learning LangGraph" logged
repeatedly), it is promoted into a durable semantic memory ("Experienced with
LangGraph"). Source memories are preserved (never deleted); a ``PROMOTED_FROM``
graph edge links the new semantic memory back to each source. Deterministic:
episodic memories are grouped by their significant-token signature; a group of
size >= ``min_occurrences`` is promoted.

Scheduler entry point: ``promote_user(user_id)`` (idempotent — a group already
promoted, recorded via a maintenance marker on its sources, is skipped).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.application.dto.graph_dto import GraphEdge, GraphEdgeType
from app.application.interfaces.event_dispatcher import EventDispatcher
from app.application.interfaces.graph_repository import GraphRepository
from app.application.interfaces.unit_of_work import UnitOfWork
from app.application.services.context.conflict_detector import STOPWORDS
from app.application.services.retrieval.bm25 import tokenize
from app.domain.entities.memory import Memory
from app.domain.value_objects.memory_category import MemoryCategory
from app.domain.value_objects.memory_status import MemoryStatus
from app.domain.value_objects.memory_type import MemoryType

_logger = logging.getLogger("memoryarena.promotion")
_PROMOTION_MARKER = "promoted_to_semantic"


@dataclass(frozen=True)
class PromotionConfig:
    min_occurrences: int = 2  # how many episodic recurrences trigger promotion


def _signature(content: str) -> frozenset[str]:
    return frozenset(t for t in tokenize(content) if t not in STOPWORDS and len(t) > 2)


def _subject(signature: frozenset[str]) -> str:
    # Deterministic, alphabetical subject phrase from the distinctive tokens.
    return " ".join(sorted(signature)).title()


class PromotionEngine:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        graph_repo: GraphRepository,
        dispatcher: EventDispatcher,
        config: PromotionConfig | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._graph = graph_repo
        self._dispatcher = dispatcher
        self._config = config or PromotionConfig()

    async def promote_user(self, user_id: UUID) -> list[UUID]:
        """Promote recurring episodic memories. Returns new semantic memory ids."""
        async with self._uow_factory() as uow:
            memories = await uow.memories.list_for_analytics(user_id)
        episodic = [
            m
            for m in memories
            if m.status is MemoryStatus.ACTIVE
            and m.category is MemoryCategory.EPISODIC
            and not m.was_swept(_PROMOTION_MARKER, "done")
        ]
        groups: dict[frozenset[str], list[Memory]] = {}
        for m in episodic:
            sig = _signature(m.content)
            if sig:
                groups.setdefault(sig, []).append(m)

        created: list[UUID] = []
        for sig, members in groups.items():
            if len(members) < self._config.min_occurrences:
                continue
            created.append(await self._promote_group(user_id, sig, members))
        return created

    async def _promote_group(
        self, user_id: UUID, signature: frozenset[str], members: list[Memory]
    ) -> UUID:
        content = f"Experienced with {_subject(signature)}"
        semantic = Memory.create(
            user_id=user_id,
            content=content,
            memory_type=MemoryType.SKILL,
            metadata={"promotion": {"reason": "recurring_episodic", "sources": len(members)}},
        )
        semantic.reclassify(MemoryCategory.SEMANTIC)
        async with self._uow_factory() as uow:
            await uow.memories.save(semantic)
            for src in members:
                src.stamp_maintenance(_PROMOTION_MARKER, "done")
                await uow.memories.update(src)
            await uow.commit()
        await self._dispatcher.dispatch(semantic.pull_events())  # embeddings + graph node

        # PROMOTED_FROM: new semantic -> each episodic source (sources preserved).
        for src in members:
            await self._graph.create_edge(
                GraphEdge(
                    source_id=str(semantic.id),
                    target_id=str(src.id),
                    edge_type=GraphEdgeType.PROMOTED_FROM,
                    weight=1.0,
                    properties={"reason": "recurring_episodic"},
                )
            )
        _logger.info(
            "promotion.created",
            extra={"semantic_id": str(semantic.id), "sources": len(members)},
        )
        return semantic.id
