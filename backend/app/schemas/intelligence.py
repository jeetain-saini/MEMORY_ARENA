"""Pydantic response schemas for the memory-intelligence endpoints (Stage 17)."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class PromotionResponseSchema(BaseModel):
    promoted: int
    semantic_ids: list[UUID]


class ForgettingResponseSchema(BaseModel):
    forgotten: int
    memory_ids: list[UUID]


class ClusterSummarySchema(BaseModel):
    cluster_id: str
    name: str
    score: float
    size: int
    member_ids: list[UUID]


class ClusteringResponseSchema(BaseModel):
    cluster_count: int
    clusters: list[ClusterSummarySchema]
