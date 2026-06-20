"""Query-Time Agent DTOs (Stage 10 Phase 4).

Plain, framework-free dataclasses describing the agent runtime's request, the
working state it threads through its stages, the trace it records, and the
response it returns. No LangGraph, no pydantic, no FastAPI — the runtime ports
and the API map to/from these.

The agent is an orchestration layer over existing MemoryArena services; these
DTOs carry only what those services already produce. ``ContextPackage`` remains
the primary artifact the answer is generated from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.application.dto.context_dto import ContextPackage
from app.application.dto.graph_dto import GraphAwareResult
from app.application.dto.retrieval_dto import RetrievalResult, RetrievedMemory
from app.domain.value_objects.memory_type import MemoryType


# --- finish reasons (string constants, not an enum, to stay JSON-trivial) ---
FINISH_COMPLETED = "completed"
FINISH_TIMEOUT = "timeout"
FINISH_MAX_ITERATIONS = "max_iterations"
FINISH_MAX_TOOL_CALLS = "max_tool_calls"
FINISH_TOKEN_BUDGET = "token_budget"
FINISH_ERROR = "error"


@dataclass(frozen=True)
class AgentConfig:
    """Tunable guardrails and budgets for a single agent run."""

    max_tokens: int = 2000            # context-assembly token budget
    answer_max_tokens: int = 512      # generated-answer token cap
    max_iterations: int = 1           # planning-round ceiling (future tool loops)
    max_tool_calls: int = 8           # total tool invocations across the run
    max_citations: int = 10           # citation count cap after validation
    timeout_seconds: float = 30.0     # whole-run wall-clock guard
    top_k: int = 10                   # retrieval breadth
    expand_graph: bool = True         # run the graph-expansion stage


@dataclass(frozen=True)
class AgentRequest:
    user_id: UUID
    query: str
    config: AgentConfig = field(default_factory=AgentConfig)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentMessage:
    role: str          # "user" | "assistant" | "tool" | "system"
    content: str


@dataclass(frozen=True)
class AgentToolCall:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentStepResult:
    step: str
    ok: bool
    summary: str = ""
    tool_call: AgentToolCall | None = None
    tokens: int = 0
    error: str | None = None


@dataclass(frozen=True)
class AgentCitation:
    memory_id: UUID
    content: str
    memory_type: MemoryType
    provenance: str    # "hybrid" | "graph"
    score: float


@dataclass(frozen=True)
class AgentTrace:
    steps: list[AgentStepResult] = field(default_factory=list)
    iterations: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
    finish_reason: str = FINISH_COMPLETED


@dataclass(frozen=True)
class AgentResponse:
    query: str
    user_id: UUID
    answer: str
    citations: list[AgentCitation]
    trace: AgentTrace
    finish_reason: str = FINISH_COMPLETED


@dataclass(frozen=True)
class AgentStreamEvent:
    """One Server-Sent-Events frame: an event name + a JSON-able payload."""

    event: str         # "step" | "answer" | "citations" | "done" | "error"
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentState:
    """Mutable working state threaded through the runtime stages.

    Both the sequential and LangGraph runtimes operate on this single state
    object (mirroring ExtractionState / ConsolidationState), so stage logic and
    guardrails are single-sourced and the two runtimes never diverge.
    """

    user_id: UUID
    query: str
    config: AgentConfig
    metadata: dict[str, Any] = field(default_factory=dict)

    # stage outputs
    retrieved: RetrievalResult | None = None
    expanded: GraphAwareResult | None = None
    context_package: ContextPackage | None = None
    answer: str = ""
    citations: list[AgentCitation] = field(default_factory=list)

    # provenance map: memory_id -> "hybrid" | "graph" (for citation validation)
    provenance: dict[UUID, str] = field(default_factory=dict)
    # candidates fed to the context builder (base hits + mapped graph memories)
    candidates: list[RetrievedMemory] = field(default_factory=list)

    # bookkeeping
    messages: list[AgentMessage] = field(default_factory=list)
    steps: list[AgentStepResult] = field(default_factory=list)
    iteration: int = 0
    tool_calls: int = 0
    total_tokens: int = 0
    finish_reason: str = FINISH_COMPLETED
    terminated: bool = False
