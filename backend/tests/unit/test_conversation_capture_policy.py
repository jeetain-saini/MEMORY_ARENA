"""Unit tests for ConversationCapturePolicy (Stage 15) — the approved matrix."""

from __future__ import annotations

import pytest

from app.application.services.agent.conversation_capture_policy import (
    ConversationCapturePolicy,
)

policy = ConversationCapturePolicy()


@pytest.mark.parametrize(
    "text",
    [
        "My name is Jeetain.",
        "I prefer dark mode.",
        "I am learning LangGraph.",
        "Building MemoryArena.",
        "Favorite language: Rust.",
        "Currently working on a GenAI startup.",
        "Skilled in FastAPI and LangChain.",
    ],
)
def test_should_capture_durable_self_disclosure(text: str) -> None:
    assert policy.should_capture(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Hi",
        "Hello",
        "Thanks",
        "Thank you",
        "ok",
        "What is FastAPI?",
        "Explain cricket.",
        "What is the capital of France?",
        "Can you help me debug this?",
    ],
)
def test_should_not_capture_noise(text: str) -> None:
    assert policy.should_capture(text) is False


def test_first_person_not_required_project_signal() -> None:
    # No first-person pronoun, but a project signal -> captured.
    assert policy.should_capture("Building a recommendation engine") is True


def test_random_trivia_without_signal_is_dropped() -> None:
    assert policy.should_capture("The capital of France is Paris") is False
    assert policy.should_capture("The moon orbits the earth") is False


def test_empty_and_short_inputs() -> None:
    assert policy.should_capture("") is False
    assert policy.should_capture("   ") is False
    assert policy.should_capture("yo") is False  # single token


def test_request_imperatives_rejected_without_question_mark() -> None:
    assert policy.should_capture("Explain how recursion works") is False
    assert policy.should_capture("Write a poem about Rust") is False


def test_min_tokens_configurable() -> None:
    strict = ConversationCapturePolicy(min_tokens=5)
    assert strict.should_capture("Building MemoryArena") is False  # 2 tokens < 5
    assert strict.should_capture("I am currently learning advanced LangGraph") is True
