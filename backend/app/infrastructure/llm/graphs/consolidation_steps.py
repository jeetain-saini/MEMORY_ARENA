"""Consolidation workflow steps — shared between Sequential and LangGraph engines.

Four steps form the consolidation pipeline:
  1. score_candidates  — filter candidates by similarity to the new memory
  2. classify_pairs    — decide UNIQUE / SUPERSEDES / CONTRADICTS / MERGE per pair
  3. enrich_reasoning  — expand reasoning for CONTRADICTS / MERGE decisions
  4. validate_decisions — clamp confidence, drop below-threshold, deduplicate

ConsolidationState is the shared mutable state threaded through all steps.
STEPS is the canonical execution order; both engines import and run it.

No LangGraph, Neo4j, SQLAlchemy, FastAPI, or Pydantic imports here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from uuid import UUID

from app.application.dto.consolidation_dto import (
    ConsolidationCandidate,
    ConsolidationDecision,
    ConsolidationDecisionType,
)
from app.application.interfaces.llm_provider import LLMProvider
from app.application.services.context._text import jaccard
from app.application.services.context.conflict_detector import NEGATION_MARKERS
from app.application.services.retrieval.bm25 import tokenize

_logger = logging.getLogger("memoryarena.consolidation")

WORKFLOW_VERSION = "consolidation-v1"

# Similarity thresholds for the sequential (Jaccard) engine.
_SCORE_THRESHOLD = 0.35       # minimum Jaccard to be worth classifying
_SUPERSEDE_JACCARD = 0.70     # high overlap → likely duplicate/supersedes
_CONTRADICT_JACCARD = 0.40    # moderate overlap + negation XOR → contradicts

# Confidence values assigned by the heuristic (sequential) engine.
_SUPERSEDE_CONFIDENCE = 0.82
_CONTRADICT_CONFIDENCE = 0.72

# Minimum confidence to keep a decision in the final list.
_MIN_CONFIDENCE = 0.50


# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

@dataclass
class ConsolidationState:
    """Mutable state passed through all pipeline steps."""
    new_memory_id: UUID
    new_content: str
    candidates: list[ConsolidationCandidate] = field(default_factory=list)
    scored_candidates: list[tuple[ConsolidationCandidate, float]] = field(default_factory=list)
    draft_decisions: list[dict] = field(default_factory=list)
    decisions: list[ConsolidationDecision] = field(default_factory=list)
    short_circuit: bool = False


# ---------------------------------------------------------------------------
# Step helpers
# ---------------------------------------------------------------------------

def _token_set(text: str) -> set[str]:
    return set(tokenize(text))


def _is_negated(tokens: list[str]) -> bool:
    return any(t in NEGATION_MARKERS for t in tokens)


def _heuristic_classify(
    new_content: str,
    candidate: ConsolidationCandidate,
    similarity: float,
) -> tuple[str, float, str]:
    """Return (relationship, confidence, reasoning) using lexical heuristics."""
    new_tokens = tokenize(new_content)
    cand_tokens = tokenize(candidate.content)

    new_negated = _is_negated(new_tokens)
    cand_negated = _is_negated(cand_tokens)

    if similarity >= _SUPERSEDE_JACCARD and len(new_content) > len(candidate.content):
        return (
            "supersedes",
            _SUPERSEDE_CONFIDENCE,
            f"High lexical overlap ({similarity:.2f}) with new memory being more detailed.",
        )

    if (
        similarity >= _CONTRADICT_JACCARD
        and new_negated != cand_negated
    ):
        return (
            "contradicts",
            _CONTRADICT_CONFIDENCE,
            (
                f"Shared subject (overlap {similarity:.2f}) with opposing negation — "
                f"one is negated, the other is not."
            ),
        )

    return ("unique", 0.0, "")


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def score_candidates(state: ConsolidationState, provider: LLMProvider) -> ConsolidationState:
    """Step 1: Score candidates by Jaccard similarity; set short_circuit if none qualify."""
    new_tokens = _token_set(state.new_content)
    scored = []
    for candidate in state.candidates:
        cand_tokens = _token_set(candidate.content)
        sim = jaccard(new_tokens, cand_tokens)
        if sim >= _SCORE_THRESHOLD:
            scored.append((candidate, sim))

    state.scored_candidates = sorted(scored, key=lambda x: x[1], reverse=True)

    if not state.scored_candidates:
        state.short_circuit = True
        _logger.debug(
            "consolidation.score.short_circuit",
            extra={"memory_id": str(state.new_memory_id)},
        )

    return state


def classify_pairs(state: ConsolidationState, provider: LLMProvider) -> ConsolidationState:
    """Step 2: Classify each scored candidate as unique/supersedes/contradicts/merge."""
    if state.short_circuit:
        return state

    drafts = []
    for candidate, similarity in state.scored_candidates:
        relationship, confidence, reasoning = _heuristic_classify(
            state.new_content, candidate, similarity
        )
        drafts.append(
            {
                "target_id": candidate.memory_id,
                "relationship": relationship,
                "confidence": confidence,
                "reasoning": reasoning,
            }
        )

    state.draft_decisions = drafts
    return state


def enrich_reasoning(state: ConsolidationState, provider: LLMProvider) -> ConsolidationState:
    """Step 3: Expand reasoning for CONTRADICTS and MERGE decisions."""
    if state.short_circuit:
        return state

    for draft in state.draft_decisions:
        if draft["relationship"] in ("contradicts", "merge") and not draft["reasoning"]:
            draft["reasoning"] = (
                f"Memory '{state.new_content[:80]}' conflicts with "
                f"an existing memory based on lexical analysis."
            )

    return state


def validate_decisions(state: ConsolidationState, provider: LLMProvider) -> ConsolidationState:
    """Step 4: Clamp, filter, deduplicate, and coerce draft decisions to typed DTOs."""
    if state.short_circuit:
        state.decisions = []
        return state

    seen: dict[UUID, ConsolidationDecision] = {}

    for draft in state.draft_decisions:
        raw_type = draft.get("relationship", "unique")
        try:
            decision_type = ConsolidationDecisionType(raw_type)
        except ValueError:
            decision_type = ConsolidationDecisionType.UNIQUE

        confidence = min(1.0, max(0.0, float(draft.get("confidence", 0.0))))

        if confidence < _MIN_CONFIDENCE and decision_type != ConsolidationDecisionType.UNIQUE:
            _logger.debug(
                "consolidation.decision.dropped",
                extra={
                    "target_id": str(draft.get("target_id")),
                    "confidence": confidence,
                    "min_confidence": _MIN_CONFIDENCE,
                },
            )
            continue

        target_id: UUID | None = draft.get("target_id")
        decision = ConsolidationDecision(
            decision_type=decision_type,
            target_id=target_id,
            reasoning=draft.get("reasoning", ""),
            confidence=confidence,
        )

        if target_id is None:
            continue  # UNIQUE decisions have no target; skip dedup

        if target_id not in seen or confidence > seen[target_id].confidence:
            seen[target_id] = decision

    state.decisions = list(seen.values())
    return state


# ---------------------------------------------------------------------------
# Canonical step order
# ---------------------------------------------------------------------------

STEPS = (score_candidates, classify_pairs, enrich_reasoning, validate_decisions)
