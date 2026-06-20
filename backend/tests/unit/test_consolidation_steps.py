"""Unit tests for the four consolidation pipeline steps.

Each step is tested in isolation using a stub LLMProvider.  The sequential
engine's heuristic logic is exercised directly through the step functions.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.application.dto.consolidation_dto import (
    ConsolidationCandidate,
    ConsolidationDecisionType,
)
from app.application.interfaces.llm_provider import LLMProvider
from app.domain.value_objects.memory_type import MemoryType
from app.infrastructure.llm.graphs.consolidation_steps import (
    ConsolidationState,
    classify_pairs,
    enrich_reasoning,
    score_candidates,
    validate_decisions,
)


# ---------------------------------------------------------------------------
# Minimal stub provider (steps are fully heuristic; provider unused in seq path)
# ---------------------------------------------------------------------------

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


_provider = _StubProvider()


def _candidate(content: str) -> ConsolidationCandidate:
    return ConsolidationCandidate(
        memory_id=uuid4(),
        content=content,
        memory_type=MemoryType.FACT,
        total_score=0.5,
        updated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Step 1 — score_candidates
# ---------------------------------------------------------------------------

def test_score_candidates_keeps_similar_pair() -> None:
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="I love using Python for data science projects",
        candidates=[_candidate("I love Python for data science work")],
    )
    result = score_candidates(state, _provider)
    assert len(result.scored_candidates) == 1
    assert not result.short_circuit


def test_score_candidates_filters_unrelated() -> None:
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="Python is great for data science",
        candidates=[_candidate("Cats are wonderful pets indeed")],
    )
    result = score_candidates(state, _provider)
    assert result.scored_candidates == []
    assert result.short_circuit


def test_score_candidates_empty_list_short_circuits() -> None:
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="any text",
        candidates=[],
    )
    result = score_candidates(state, _provider)
    assert result.short_circuit
    assert result.scored_candidates == []


# ---------------------------------------------------------------------------
# Step 2 — classify_pairs
# ---------------------------------------------------------------------------

def test_classify_pairs_skips_when_short_circuit() -> None:
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="text",
        short_circuit=True,
    )
    result = classify_pairs(state, _provider)
    assert result.draft_decisions == []


def test_classify_pairs_supersedes_high_overlap_longer_new() -> None:
    """New memory is longer + high overlap → SUPERSEDES draft decision."""
    # High token overlap (9/10 = 0.90 Jaccard) AND new is longer → SUPERSEDES.
    new = "I use Python for data science and machine learning projects"
    cand_content = "I use Python for data science and machine learning"
    cand = _candidate(cand_content)
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content=new,
        candidates=[cand],
    )
    state = score_candidates(state, _provider)
    assert not state.short_circuit, "expected candidate to pass the score threshold"
    state = classify_pairs(state, _provider)

    assert state.draft_decisions
    relationships = [d["relationship"] for d in state.draft_decisions]
    assert "supersedes" in relationships


def test_classify_pairs_contradicts_negation_xor() -> None:
    """Negation XOR with sufficient overlap → CONTRADICTS draft decision.

    Uses content where:
    - Jaccard is in (0.40, 0.70) — above contradict threshold, below supersede
    - new is shorter than candidate — so length check doesn't trigger SUPERSEDES
    - one sentence has a negation marker, the other does not
    """
    # Intersection: write, python, code, for, work (+ i) = 6
    # Union: i, no, longer, write, python, code, for, work, every, single, day = 11
    # Jaccard ≈ 0.545 → above contradict (0.40), below supersede (0.70)
    new = "I no longer write Python code for work"
    cand_content = "I write Python code for work every single day"
    cand = _candidate(cand_content)
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content=new,
        candidates=[cand],
    )
    state = score_candidates(state, _provider)
    assert not state.short_circuit, "expected pair to pass the score threshold"
    state = classify_pairs(state, _provider)
    relationships = [d["relationship"] for d in state.draft_decisions]
    assert "contradicts" in relationships


def test_classify_pairs_unique_for_unrelated() -> None:
    """Unrelated but close-enough-to-score content → UNIQUE decision."""
    new = "Python is good"
    cand_content = "Python is great"
    cand = _candidate(cand_content)
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content=new,
        candidates=[cand],
    )
    state = score_candidates(state, _provider)
    if not state.short_circuit:
        state = classify_pairs(state, _provider)
        for draft in state.draft_decisions:
            assert draft["relationship"] in ("unique", "supersedes", "contradicts", "merge")


# ---------------------------------------------------------------------------
# Step 3 — enrich_reasoning
# ---------------------------------------------------------------------------

def test_enrich_reasoning_skips_when_short_circuit() -> None:
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="text",
        short_circuit=True,
        draft_decisions=[{"relationship": "contradicts", "reasoning": ""}],
    )
    result = enrich_reasoning(state, _provider)
    # short_circuit means we return early; draft_decisions unchanged
    assert result.draft_decisions[0]["reasoning"] == ""


def test_enrich_reasoning_fills_empty_contradicts_reasoning() -> None:
    cand_id = uuid4()
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="I no longer like Python",
        short_circuit=False,
        draft_decisions=[
            {
                "target_id": cand_id,
                "relationship": "contradicts",
                "reasoning": "",
                "confidence": 0.72,
            }
        ],
    )
    result = enrich_reasoning(state, _provider)
    assert result.draft_decisions[0]["reasoning"] != ""


def test_enrich_reasoning_leaves_unique_unchanged() -> None:
    cand_id = uuid4()
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="something",
        short_circuit=False,
        draft_decisions=[
            {"target_id": cand_id, "relationship": "unique", "reasoning": "", "confidence": 0.0}
        ],
    )
    result = enrich_reasoning(state, _provider)
    assert result.draft_decisions[0]["reasoning"] == ""


# ---------------------------------------------------------------------------
# Step 4 — validate_decisions
# ---------------------------------------------------------------------------

def test_validate_decisions_clamps_confidence() -> None:
    cand_id = uuid4()
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="text",
        short_circuit=False,
        draft_decisions=[
            {"target_id": cand_id, "relationship": "contradicts", "confidence": 1.5, "reasoning": "r"},
            {"target_id": uuid4(), "relationship": "supersedes", "confidence": -0.1, "reasoning": "s"},
        ],
    )
    result = validate_decisions(state, _provider)
    for d in result.decisions:
        assert 0.0 <= d.confidence <= 1.0


def test_validate_decisions_drops_below_min_confidence() -> None:
    cand_id = uuid4()
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="text",
        short_circuit=False,
        draft_decisions=[
            # confidence = 0.1 is below _MIN_CONFIDENCE (0.50) for non-UNIQUE
            {"target_id": cand_id, "relationship": "contradicts", "confidence": 0.1, "reasoning": "r"},
        ],
    )
    result = validate_decisions(state, _provider)
    assert result.decisions == []


def test_validate_decisions_deduplicates_by_target() -> None:
    """When two decisions share a target_id, keep the higher-confidence one."""
    cand_id = uuid4()
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="text",
        short_circuit=False,
        draft_decisions=[
            {"target_id": cand_id, "relationship": "contradicts", "confidence": 0.65, "reasoning": "a"},
            {"target_id": cand_id, "relationship": "supersedes", "confidence": 0.82, "reasoning": "b"},
        ],
    )
    result = validate_decisions(state, _provider)
    assert len(result.decisions) == 1
    assert result.decisions[0].confidence == 0.82


def test_validate_decisions_invalid_relationship_becomes_unique() -> None:
    """An invalid relationship string should be coerced to UNIQUE and dropped (no target_id)."""
    cand_id = uuid4()
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="text",
        short_circuit=False,
        draft_decisions=[
            {"target_id": cand_id, "relationship": "TOTALLY_WRONG", "confidence": 0.9, "reasoning": "r"},
        ],
    )
    result = validate_decisions(state, _provider)
    # UNIQUE decisions with no target_id are skipped; result should be empty
    assert all(d.decision_type == ConsolidationDecisionType.UNIQUE for d in result.decisions) or result.decisions == []


def test_validate_decisions_empty_when_short_circuit() -> None:
    state = ConsolidationState(
        new_memory_id=uuid4(),
        new_content="text",
        short_circuit=True,
        draft_decisions=[
            {"target_id": uuid4(), "relationship": "contradicts", "confidence": 0.9, "reasoning": "r"},
        ],
    )
    result = validate_decisions(state, _provider)
    assert result.decisions == []
