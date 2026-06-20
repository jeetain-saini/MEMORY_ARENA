"""Provider-selection tests for the context compressor factory."""

from __future__ import annotations

import os

import pytest

from app.application.services.context.compressor import HeuristicContextCompressor
from app.infrastructure.llm.compressors.llm_compressor import LLMContextCompressor


def _set_env() -> None:
    os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    os.environ.setdefault("NEO4J_USERNAME", "neo4j")
    os.environ.setdefault("NEO4J_PASSWORD", "secret")
    os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")


def test_factory_defaults_to_heuristic(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.infrastructure.llm.compressors.factory import build_context_compressor

    _set_env()
    monkeypatch.delenv("CONTEXT_COMPRESSOR", raising=False)
    get_settings.cache_clear()
    build_context_compressor.cache_clear()
    assert isinstance(build_context_compressor(), HeuristicContextCompressor)

    get_settings.cache_clear()
    build_context_compressor.cache_clear()


def test_factory_selects_compressor_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.infrastructure.llm.compressors.factory import build_context_compressor

    _set_env()
    for value, expected in (
        ("heuristic", HeuristicContextCompressor),
        ("llm", LLMContextCompressor),
    ):
        monkeypatch.setenv("CONTEXT_COMPRESSOR", value)
        get_settings.cache_clear()
        build_context_compressor.cache_clear()
        assert isinstance(build_context_compressor(), expected)

    get_settings.cache_clear()
    build_context_compressor.cache_clear()


def test_factory_llm_compressor_has_heuristic_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.infrastructure.llm.compressors.factory import build_context_compressor

    _set_env()
    monkeypatch.setenv("CONTEXT_COMPRESSOR", "llm")
    get_settings.cache_clear()
    build_context_compressor.cache_clear()
    compressor = build_context_compressor()
    assert isinstance(compressor, LLMContextCompressor)
    assert isinstance(compressor._fallback, HeuristicContextCompressor)

    get_settings.cache_clear()
    build_context_compressor.cache_clear()


def test_factory_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.infrastructure.llm.compressors.factory import build_context_compressor

    _set_env()
    monkeypatch.setenv("CONTEXT_COMPRESSOR", "LLM")
    get_settings.cache_clear()
    build_context_compressor.cache_clear()
    assert isinstance(build_context_compressor(), LLMContextCompressor)

    get_settings.cache_clear()
    build_context_compressor.cache_clear()
