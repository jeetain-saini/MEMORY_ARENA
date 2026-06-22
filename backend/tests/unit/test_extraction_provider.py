"""Unit tests: memory extraction provider is decoupled from answer generation."""

from __future__ import annotations

import os

os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")

import pytest  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.infrastructure.llm.providers.deterministic_provider import (  # noqa: E402
    DeterministicLLMProvider,
)
from app.infrastructure.llm.providers.factory import (  # noqa: E402
    build_extraction_llm_provider,
    build_llm_provider,
)
from app.infrastructure.llm.providers.nvidia_provider import NvidiaProvider  # noqa: E402


def _clear() -> None:
    get_settings.cache_clear()
    build_llm_provider.cache_clear()
    build_extraction_llm_provider.cache_clear()


def _base(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    monkeypatch.setenv("JWT_SECRET", "a-sufficiently-long-secret")


def test_extraction_defaults_to_deterministic_while_answer_uses_nvidia(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-test")
    monkeypatch.setenv("LLM_MODEL", "minimaxai/minimax-m3")
    monkeypatch.delenv("EXTRACTION_LLM_PROVIDER", raising=False)
    _clear()
    try:
        # Answer generation stays on NVIDIA...
        assert isinstance(build_llm_provider(), NvidiaProvider)
        # ...while extraction is the local, free, rule-based provider.
        assert isinstance(build_extraction_llm_provider(), DeterministicLLMProvider)
    finally:
        _clear()


def test_extraction_provider_is_overridable(monkeypatch: pytest.MonkeyPatch) -> None:
    _base(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "deterministic")
    monkeypatch.setenv("EXTRACTION_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-test")
    monkeypatch.setenv("LLM_MODEL", "m")
    _clear()
    try:
        assert isinstance(build_extraction_llm_provider(), NvidiaProvider)
    finally:
        _clear()


def test_answer_and_extraction_providers_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _base(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-test")
    monkeypatch.setenv("EXTRACTION_LLM_PROVIDER", "deterministic")
    _clear()
    try:
        answer = build_llm_provider()
        extraction = build_extraction_llm_provider()
        assert type(answer) is not type(extraction)
        assert isinstance(answer, NvidiaProvider)
        assert isinstance(extraction, DeterministicLLMProvider)
    finally:
        _clear()
