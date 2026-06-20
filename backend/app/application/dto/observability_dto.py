"""Observability DTOs (Stage 13).

Request-scoped, deterministic *explain* objects for a single agent run. They
answer "why was this retrieved / expanded / put in context / how long did each
stage take" from data the pipeline already produced — they carry no new
capability and never re-run any subsystem.

Plain frozen dataclasses (no pydantic, no framework). The API maps its schemas
to/from these; the trace recorder (Phase B) records them. A ``RequestTrace`` is
assembled at the agent-orchestration boundary, where the retrieval, graph, and
context results coexist on the agent state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class StepTiming:
    """How long one pipeline stage took (monotonic, milliseconds)."""

    step: str
    duration_ms: float
    ok: bool = True


@dataclass(frozen=True)
class RetrievalTrace:
    """Why the retrieval stage returned what it did."""

    query: str
    candidate_count: int          # candidates the agent saw from hybrid retrieval
    returned_count: int           # results carried forward
    top_scores: list[float] = field(default_factory=list)  # final scores, ranked
    duration_ms: float = 0.0


@dataclass(frozen=True)
class SeedExpansion:
    """Per-seed graph expansion outcome."""

    seed_memory_id: UUID
    neighbors_admitted: int


@dataclass(frozen=True)
class GraphExpansionTrace:
    """Why graph expansion surfaced the neighbors it did."""

    enabled: bool
    hybrid_count: int             # direct (hybrid-provenance) hits
    graph_count: int              # neighbors admitted via the graph
    influence_scores: list[float] = field(default_factory=list)  # decayed neighbor scores
    seeds: list[SeedExpansion] = field(default_factory=list)
    duration_ms: float = 0.0


@dataclass(frozen=True)
class ContextTrace:
    """Why the context package looks the way it does (budget view)."""

    memory_count: int
    total_tokens: int
    max_tokens: int
    budget_utilization: float     # total_tokens / max_tokens, clamped to [0, 1+]
    duration_ms: float = 0.0


@dataclass(frozen=True)
class RequestTrace:
    """The full, request-scoped explanation of one agent run."""

    query: str
    user_id: UUID
    finish_reason: str
    total_duration_ms: float
    timings: list[StepTiming] = field(default_factory=list)
    retrieval: RetrievalTrace | None = None
    graph: GraphExpansionTrace | None = None
    context: ContextTrace | None = None
    iterations: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
