"""Unit tests for the Knowledge Inference Layer (Phase A).

Deterministic, no LLM — every example from the product spec is asserted here.
"""

from __future__ import annotations

import pytest

from app.application.services.inference.knowledge_inference import infer
from app.domain.value_objects.memory_type import MemoryType


@pytest.mark.parametrize(
    "text,statement,mtype",
    [
        # Technology interest (from questions)
        ("What is Rust?", "Interested in Rust", MemoryType.PREFERENCE),
        ("What is FastAPI?", "Interested in FastAPI", MemoryType.PREFERENCE),
        ("Explain Neo4j.", "Interested in Neo4j", MemoryType.PREFERENCE),
        ("What is LangGraph?", "Interested in LangGraph", MemoryType.PREFERENCE),
        ("What is Docker?", "Interested in Docker", MemoryType.PREFERENCE),
        # Learning progression
        ("Teach me Rust.", "Learning Rust", MemoryType.SKILL),
        ("Can you teach me Kubernetes?", "Learning Kubernetes", MemoryType.SKILL),
        # Usage
        ("I'm building a Rust API.", "Uses Rust", MemoryType.SKILL),
        ("I built a FastAPI backend.", "Uses FastAPI", MemoryType.SKILL),
        # Experience
        ("I've been developing Rust systems for two years.", "Experienced with Rust", MemoryType.SKILL),
        # Career
        ("I want to become an ML Engineer.", "Career goal: ML Engineer", MemoryType.GOAL),
        # Projects
        ("I'm building a RAG chatbot.", "Current project: RAG Chatbot", MemoryType.PROJECT),
        ("I finished my RAG chatbot.", "Completed project: RAG Chatbot", MemoryType.PROJECT),
        # Goals
        ("I want to lose weight.", "Goal: Lose Weight", MemoryType.GOAL),
        ("I'm focusing on muscle gain.", "Goal: Muscle Gain", MemoryType.GOAL),
        # Internship
        ("My internship starts next month.", "Upcoming internship", MemoryType.EXPERIENCE),
        ("I completed my internship.", "Completed internship", MemoryType.EXPERIENCE),
    ],
)
def test_infers_expected_statement(text: str, statement: str, mtype: MemoryType) -> None:
    result = infer(text)
    assert result is not None, f"expected inference for {text!r}"
    assert result.statement == statement
    assert result.memory_type == mtype


def test_never_stores_raw_question() -> None:
    result = infer("What is Rust?")
    assert result is not None
    assert "?" not in result.statement
    assert result.statement != "What is Rust?"


@pytest.mark.parametrize(
    "text",
    [
        "What is the weather today?",   # no durable knowledge / unknown topic
        "Can you summarize this email?",  # request, no topic
        "hello there",                   # greeting / temporary chat
        "thanks!",                       # acknowledgement
        "",                               # empty
    ],
)
def test_returns_none_for_non_knowledge(text: str) -> None:
    assert infer(text) is None


def test_every_result_has_metadata() -> None:
    result = infer("Teach me Rust.")
    assert result is not None
    assert 0.0 <= result.confidence <= 1.0
    assert 0.0 <= result.importance <= 1.0
    assert result.reason  # reason_for_inference is non-empty


def test_progression_strengthens_signal() -> None:
    """Confidence should rise across the interest -> learning -> uses -> expert arc."""
    interest = infer("What is Rust?")
    learning = infer("Teach me Rust.")
    uses = infer("I'm building a Rust API.")
    experienced = infer("I've used Rust for 2 years.")
    assert interest and learning and uses and experienced
    assert interest.confidence < learning.confidence < uses.confidence <= experienced.confidence
