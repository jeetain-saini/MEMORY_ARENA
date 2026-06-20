"""Pydantic schemas for the Query-Time Agent API (API v1).

The wire contract for ``POST /query`` and ``POST /query/stream``. The request is
deliberately minimal (``user_id`` + ``query``); guardrails come from server-side
configuration. The response surfaces the generated ``answer`` and validated
``citations``.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from app.application.dto.agent_dto import AgentConfig, AgentRequest, AgentResponse
from app.domain.value_objects.memory_type import MemoryType
from app.schemas.observability import RequestTraceSchema


class QueryRequestSchema(BaseModel):
    user_id: UUID
    query: str = Field(min_length=1, max_length=10_000)

    def to_request(self, config: AgentConfig) -> AgentRequest:
        return AgentRequest(user_id=self.user_id, query=self.query, config=config)


class CitationSchema(BaseModel):
    memory_id: UUID
    content: str
    memory_type: MemoryType
    provenance: str
    score: float


class QueryResponseSchema(BaseModel):
    answer: str
    citations: list[CitationSchema]
    finish_reason: str
    trace: RequestTraceSchema | None = None

    @classmethod
    def from_dto(cls, dto: AgentResponse) -> "QueryResponseSchema":
        return cls(
            answer=dto.answer,
            citations=[
                CitationSchema(
                    memory_id=c.memory_id,
                    content=c.content,
                    memory_type=c.memory_type,
                    provenance=c.provenance,
                    score=c.score,
                )
                for c in dto.citations
            ],
            finish_reason=dto.finish_reason,
            trace=(
                RequestTraceSchema.from_dto(dto.request_trace)
                if dto.request_trace is not None
                else None
            ),
        )
