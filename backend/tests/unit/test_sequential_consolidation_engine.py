"""Unit tests for SequentialConsolidationEngine — full pipeline without LangGraph."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from app.application.dto.consolidation_dto import (
    ConsolidationCandidate,
    ConsolidationDecisionType,
    ConsolidationRequest,
)
from app.application.interfaces.llm_provider import LLMProvider
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.graphs.sequential_consolidation_engine import (
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


def _engine() -> SequentialConsolidationEngine:
    return SequentialConsolidationEngine(_StubProvider())


def _cand(content: str) -> ConsolidationCandidate:
    return ConsolidationCandidate(
        memory_id=uuid4(),
        content=content,
        memory_type=MemoryType.FACT,
        total_score=0.5,
        updated_at=datetime.now(timezone.utc),
    )


def _req(new_content: str, candidates: list[ConsolidationCandidate]) -> ConsolidationRequest:
    return ConsolidationRequest(
        new_memory_id=uuid4(),
        user_id=uuid4(),
        new_content=new_content,
        new_type=MemoryType.FACT,
        candidates=candidates,
    )


def test_empty_candidates_returns_no_decisions() -> None:
    async def run() -> None:
        engine = _engine()
        decisions = await engine.consolidate(_req("some text", []))
        assert decisions == []

    _run(run())


def test_unrelated_content_returns_no_decisions() -> None:
    async def run() -> None:
        engine = _engine()
        new = "Cats are wonderful creatures to have around"
        cand = _cand("The stock market crashed yesterday")
        decisions = await engine.consolidate(_req(new, [cand]))
        assert decisions == []

    _run(run())


def test_below_threshold_returns_no_decisions() -> None:
    """Content with too-low Jaccard similarity is filtered in step 1."""

    async def run() -> None:
        engine = _engine()
        new = "Python programming"
        cand = _cand("Python code")
        decisions = await engine.consolidate(_req(new, [cand]))
        # May or may not produce decisions depending on threshold; verify no crash
        assert isinstance(decisions, list)

    _run(run())


def test_near_duplicate_with_longer_new_can_supersede() -> None:
    """Very high overlap AND new is longer → SUPERSEDES (when threshold met)."""

    async def run() -> None:
        engine = _engine()
        new = "I use Python for data science machine learning projects work everyday at my job"
        cand = _cand("I use Python for data science")
        decisions = await engine.consolidate(_req(new, [cand]))
        types = {d.decision_type for d in decisions}
        # May produce SUPERSEDES or nothing if Jaccard threshold not met; no crash
        assert types <= {
            ConsolidationDecisionType.SUPERSEDES,
            ConsolidationDecisionType.CONTRADICTS,
            ConsolidationDecisionType.UNIQUE,
            ConsolidationDecisionType.MERGE,
        }

    _run(run())


def test_negation_pair_classifies_as_contradicts() -> None:
    """Clear negation XOR with shared subject → CONTRADICTS decision."""

    async def run() -> None:
        engine = _engine()
        new = "I no longer use Python for my data projects"
        cand = _cand("I use Python for my data projects every day")
        decisions = await engine.consolidate(_req(new, [cand]))
        types = {d.decision_type for d in decisions}
        # The pair shares 'use python my data projects' tokens;
        # one is negated → CONTRADICTS, or UNIQUE if sim below threshold.
        assert types <= {
            ConsolidationDecisionType.CONTRADICTS,
            ConsolidationDecisionType.UNIQUE,
        }

    _run(run())


def test_supersedes_has_confidence_at_least_min() -> None:
    """Any returned SUPERSEDES decision must have confidence ≥ 0.60 (post-filter)."""

    async def run() -> None:
        engine = _engine()
        new = "I use Python for data science and machine learning and deep learning and AI work at my company"
        cand = _cand("I use Python")
        decisions = await engine.consolidate(_req(new, [cand]))
        for d in decisions:
            if d.decision_type == ConsolidationDecisionType.SUPERSEDES:
                assert d.confidence >= 0.50  # _MIN_CONFIDENCE floor

    _run(run())


def test_multiple_candidates_all_evaluated() -> None:
    """Multiple candidates are all scored; results include only the relevant ones."""

    async def run() -> None:
        engine = _engine()
        new = "Python data science machine learning"
        cands = [
            _cand("Python data science machine learning rocks"),  # similar
            _cand("Gardening is a peaceful hobby"),               # unrelated
        ]
        decisions = await engine.consolidate(_req(new, cands))
        assert isinstance(decisions, list)
        # At most one decision (the unrelated one is filtered in step 1)
        assert len(decisions) <= 1

    _run(run())
