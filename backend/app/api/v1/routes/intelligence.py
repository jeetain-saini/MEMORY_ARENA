"""Memory-intelligence API endpoints (API v1, Stage 17).

Manual/scheduler entry points for the self-evolving memory engines:

* ``POST /intelligence/promote/{user_id}`` — promote recurring episodic memories
  into semantic ones (writes PROMOTED_FROM edges; sources preserved).
* ``POST /intelligence/forget/{user_id}``  — sweep eligible memories to FORGOTTEN.
* ``POST /intelligence/cluster/{user_id}``  — (re)compute semantic clusters and
  write CLUSTER_MEMBER edges.

These orchestrate existing engines; they do not change retrieval, capture, or
contradiction resolution.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.v1.dependencies.providers import (
    CurrentPrincipalDep,
    get_clustering_engine,
    get_forgetting_engine,
    get_promotion_engine,
)
from app.application.dto.auth_dto import AuthPrincipal
from app.application.services.authorization import authorize_owner
from app.application.services.intelligence.clustering_engine import ClusteringEngine
from app.application.services.intelligence.forgetting_engine import (
    ForgettingConfig,
    ForgettingEngine,
)
from app.application.services.intelligence.promotion_engine import PromotionEngine
from app.schemas.intelligence import (
    ClusterSummarySchema,
    ClusteringResponseSchema,
    ForgettingResponseSchema,
    PromotionResponseSchema,
)

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.post("/promote/{user_id}", response_model=PromotionResponseSchema)
async def promote(
    user_id: UUID,
    engine: PromotionEngine = Depends(get_promotion_engine),
    principal: AuthPrincipal | None = CurrentPrincipalDep,
) -> PromotionResponseSchema:
    if principal is not None:
        authorize_owner(principal, user_id)
    created = await engine.promote_user(user_id)
    return PromotionResponseSchema(promoted=len(created), semantic_ids=created)


@router.post("/forget/{user_id}", response_model=ForgettingResponseSchema)
async def forget(
    user_id: UUID,
    min_age_days: int | None = None,
    max_importance: float | None = None,
    engine: ForgettingEngine = Depends(get_forgetting_engine),
    principal: AuthPrincipal | None = CurrentPrincipalDep,
) -> ForgettingResponseSchema:
    if principal is not None:
        authorize_owner(principal, user_id)
    # Optional per-call threshold overrides (operators/scheduler may tune these).
    config = None
    if min_age_days is not None or max_importance is not None:
        config = ForgettingConfig(
            min_age_days=min_age_days if min_age_days is not None else 90,
            max_importance=max_importance if max_importance is not None else 0.25,
        )
    forgotten = await engine.sweep_user(user_id, config=config)
    return ForgettingResponseSchema(forgotten=len(forgotten), memory_ids=forgotten)


@router.post("/cluster/{user_id}", response_model=ClusteringResponseSchema)
async def cluster(
    user_id: UUID,
    engine: ClusteringEngine = Depends(get_clustering_engine),
    principal: AuthPrincipal | None = CurrentPrincipalDep,
) -> ClusteringResponseSchema:
    if principal is not None:
        authorize_owner(principal, user_id)
    clusters = await engine.cluster_user(user_id)
    return ClusteringResponseSchema(
        cluster_count=len(clusters),
        clusters=[
            ClusterSummarySchema(
                cluster_id=c.cluster_id, name=c.name, score=c.score,
                size=c.size, member_ids=c.member_ids,
            )
            for c in clusters
        ],
    )
