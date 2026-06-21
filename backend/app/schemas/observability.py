"""Pydantic schemas for Stage 13 observability traces.

The wire contract for the request-scoped ``RequestTrace`` (surfaced additively on
``/query`` and listed by ``GET /observability/traces``). Mapped from the
framework-free ``observability_dto`` DTOs at the edge.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.application.dto.metrics_dto import MetricsSnapshot
from app.application.dto.observability_dto import RequestTrace


class StepTimingSchema(BaseModel):
    step: str
    duration_ms: float
    ok: bool


class RetrievalTraceSchema(BaseModel):
    query: str
    candidate_count: int
    returned_count: int
    top_scores: list[float]
    duration_ms: float


class SeedExpansionSchema(BaseModel):
    seed_memory_id: UUID
    neighbors_admitted: int


class GraphExpansionTraceSchema(BaseModel):
    enabled: bool
    hybrid_count: int
    graph_count: int
    influence_scores: list[float]
    seeds: list[SeedExpansionSchema]
    duration_ms: float


class ContextTraceSchema(BaseModel):
    memory_count: int
    total_tokens: int
    max_tokens: int
    budget_utilization: float
    duration_ms: float


class RequestTraceSchema(BaseModel):
    query: str
    user_id: UUID
    finish_reason: str
    total_duration_ms: float
    timings: list[StepTimingSchema]
    retrieval: RetrievalTraceSchema | None = None
    graph: GraphExpansionTraceSchema | None = None
    context: ContextTraceSchema | None = None
    iterations: int
    tool_calls: int
    total_tokens: int

    @classmethod
    def from_dto(cls, dto: RequestTrace) -> "RequestTraceSchema":
        return cls(
            query=dto.query,
            user_id=dto.user_id,
            finish_reason=dto.finish_reason,
            total_duration_ms=dto.total_duration_ms,
            timings=[
                StepTimingSchema(step=t.step, duration_ms=t.duration_ms, ok=t.ok)
                for t in dto.timings
            ],
            retrieval=(
                RetrievalTraceSchema(
                    query=dto.retrieval.query,
                    candidate_count=dto.retrieval.candidate_count,
                    returned_count=dto.retrieval.returned_count,
                    top_scores=dto.retrieval.top_scores,
                    duration_ms=dto.retrieval.duration_ms,
                )
                if dto.retrieval is not None
                else None
            ),
            graph=(
                GraphExpansionTraceSchema(
                    enabled=dto.graph.enabled,
                    hybrid_count=dto.graph.hybrid_count,
                    graph_count=dto.graph.graph_count,
                    influence_scores=dto.graph.influence_scores,
                    seeds=[
                        SeedExpansionSchema(
                            seed_memory_id=s.seed_memory_id,
                            neighbors_admitted=s.neighbors_admitted,
                        )
                        for s in dto.graph.seeds
                    ],
                    duration_ms=dto.graph.duration_ms,
                )
                if dto.graph is not None
                else None
            ),
            context=(
                ContextTraceSchema(
                    memory_count=dto.context.memory_count,
                    total_tokens=dto.context.total_tokens,
                    max_tokens=dto.context.max_tokens,
                    budget_utilization=dto.context.budget_utilization,
                    duration_ms=dto.context.duration_ms,
                )
                if dto.context is not None
                else None
            ),
            iterations=dto.iterations,
            tool_calls=dto.tool_calls,
            total_tokens=dto.total_tokens,
        )


# --- performance metrics (Stage 14 Phase 5) -------------------------------
class LatencyStatSchema(BaseModel):
    count: int
    avg_ms: float
    p50_ms: float
    p95_ms: float


class MetricsSnapshotSchema(BaseModel):
    counters: dict[str, int]
    latencies: dict[str, LatencyStatSchema]

    @classmethod
    def from_dto(cls, dto: MetricsSnapshot) -> "MetricsSnapshotSchema":
        return cls(
            counters=dict(dto.counters),
            latencies={
                name: LatencyStatSchema(
                    count=stat.count, avg_ms=stat.avg_ms, p50_ms=stat.p50_ms, p95_ms=stat.p95_ms
                )
                for name, stat in dto.latencies.items()
            },
        )
