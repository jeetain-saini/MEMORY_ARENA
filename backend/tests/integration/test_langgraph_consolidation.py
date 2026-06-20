"""Integration: LangGraphConsolidationEngine produces same decisions as sequential.

Skip-guarded: the entire module is skipped when langgraph is not installed
(matching the pattern in test_langgraph_extraction.py).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

import pytest

pytest.importorskip("langgraph")

from app.application.dto.consolidation_dto import (  # noqa: E402
    ConsolidationCandidate,
    ConsolidationRequest,
)
from app.application.interfaces.llm_provider import LLMProvider  # noqa: E402
from app.domain.value_objects.memory_type import MemoryType  # noqa: E402
from app.infrastructure.llm.graphs.consolidation_graph import (  # noqa: E402
    LangGraphConsolidationEngine,
)
from app.infrastructure.llm.graphs.sequential_consolidation_engine import (  # noqa: E402
    SequentialConsolidationEngine,
)


class _StubProvider(LLMProvider):
    @property
    def model_name(self) -> str:
        return "stub"

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        return ""

    async def structured_generate(self, prompt, *, schema, system=None):
        return {}

    async def health_check(self) -> bool:
        return True


def _run(coro):
    return asyncio.run(coro)


def _cand(content: str) -> ConsolidationCandidate:
    return ConsolidationCandidate(
        memory_id=uuid4(),
        content=content,
        memory_type=MemoryType.FACT,
        total_score=0.5,
        updated_at=datetime.now(timezone.utc),
    )


def _req(new_content: str, candidates: list) -> ConsolidationRequest:
    return ConsolidationRequest(
        new_memory_id=uuid4(),
        user_id=uuid4(),
        new_content=new_content,
        new_type=MemoryType.FACT,
        candidates=candidates,
    )


def test_langgraph_engine_empty_candidates() -> None:
    """Empty candidate list → no decisions (short_circuit path)."""
    engine = LangGraphConsolidationEngine(_StubProvider())
    decisions = _run(engine.consolidate(_req("some text", [])))
    assert decisions == []


def test_langgraph_engine_unrelated_returns_no_decisions() -> None:
    engine = LangGraphConsolidationEngine(_StubProvider())
    new = "Cats are wonderful creatures"
    cand = _cand("The stock market crashed yesterday")
    decisions = _run(engine.consolidate(_req(new, [cand])))
    assert decisions == []


def test_langgraph_matches_sequential_engine_on_similar_content() -> None:
    """LangGraph and sequential engines must produce the same decision types."""
    provider = _StubProvider()
    lg_engine = LangGraphConsolidationEngine(provider)
    seq_engine = SequentialConsolidationEngine(provider)

    new = "I no longer use Python for my data projects at work"
    cands = [_cand("I use Python for my data projects at work every day")]
    req = _req(new, cands)

    lg_decisions = _run(lg_engine.consolidate(req))
    seq_decisions = _run(seq_engine.consolidate(req))

    lg_types = {d.decision_type for d in lg_decisions}
    seq_types = {d.decision_type for d in seq_decisions}
    assert lg_types == seq_types
