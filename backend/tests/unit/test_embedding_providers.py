"""Tests for the embedding providers and the provider factory."""

from __future__ import annotations

import asyncio
import os
from types import SimpleNamespace

import pytest

from app.infrastructure.embeddings.bge_provider import LocalBGEEmbeddingProvider
from app.infrastructure.embeddings.deterministic_provider import DeterministicEmbeddingProvider
from app.infrastructure.embeddings.openai_provider import OpenAIEmbeddingProvider


# --- DeterministicEmbeddingProvider ----------------------------------------
def test_deterministic_dimensions_and_range() -> None:
    provider = DeterministicEmbeddingProvider(dimensions=32)
    vector = asyncio.run(provider.embed_text("hello"))
    assert len(vector) == 32
    assert all(-1.0 <= v <= 1.0 for v in vector)
    assert provider.dimensions == 32
    assert provider.model_name == "deterministic-hash-v1"


def test_deterministic_is_reproducible() -> None:
    p = DeterministicEmbeddingProvider(dimensions=16)
    assert asyncio.run(p.embed_text("same")) == asyncio.run(p.embed_text("same"))
    assert asyncio.run(p.embed_text("a")) != asyncio.run(p.embed_text("b"))


def test_deterministic_batch() -> None:
    p = DeterministicEmbeddingProvider(dimensions=8)
    vectors = asyncio.run(p.embed_batch(["a", "b", "c"]))
    assert len(vectors) == 3 and all(len(v) == 8 for v in vectors)


def test_deterministic_rejects_bad_dimensions() -> None:
    with pytest.raises(ValueError):
        DeterministicEmbeddingProvider(dimensions=0)


def test_deterministic_health_is_true() -> None:
    assert asyncio.run(DeterministicEmbeddingProvider().health_check()) is True


# --- OpenAIEmbeddingProvider (injected fake client) ------------------------
class _FakeEmbeddings:
    async def create(self, *, model, input, dimensions):
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.1] * dimensions) for _ in input])


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.embeddings = _FakeEmbeddings()


def test_openai_embed_with_fake_client() -> None:
    provider = OpenAIEmbeddingProvider(api_key=None, dimensions=4, client=_FakeOpenAIClient())
    assert asyncio.run(provider.embed_text("x")) == [0.1, 0.1, 0.1, 0.1]
    batch = asyncio.run(provider.embed_batch(["a", "b"]))
    assert len(batch) == 2


def test_openai_health_reflects_config() -> None:
    assert asyncio.run(OpenAIEmbeddingProvider(api_key="sk-test").health_check()) is True
    assert asyncio.run(OpenAIEmbeddingProvider(api_key=None).health_check()) is False


def test_openai_without_key_or_client_raises() -> None:
    provider = OpenAIEmbeddingProvider(api_key=None)
    with pytest.raises(RuntimeError):
        asyncio.run(provider.embed_text("x"))


# --- LocalBGEEmbeddingProvider (injected fake model) -----------------------
class _FakeModel:
    def encode(self, texts, normalize_embeddings=False):
        return [[0.2, 0.3] for _ in texts]


def test_bge_embed_with_fake_model() -> None:
    provider = LocalBGEEmbeddingProvider(model=_FakeModel(), dimensions=2)
    assert asyncio.run(provider.embed_text("x")) == [0.2, 0.3]
    assert asyncio.run(provider.health_check()) is True
    assert provider.model_name == "BAAI/bge-small-en-v1.5"


# --- Factory ----------------------------------------------------------------
def _set_env() -> None:
    os.environ.setdefault("POSTGRES_URL", "postgresql+asyncpg://u:p@localhost:5432/db")
    os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
    os.environ.setdefault("NEO4J_URI", "bolt://localhost:7687")
    os.environ.setdefault("NEO4J_USERNAME", "neo4j")
    os.environ.setdefault("NEO4J_PASSWORD", "secret")
    os.environ.setdefault("JWT_SECRET", "a-sufficiently-long-secret")


def test_factory_selects_provider_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings
    from app.infrastructure.embeddings.factory import build_embedding_provider

    _set_env()
    for value, expected in (
        ("hash", DeterministicEmbeddingProvider),
        ("openai", OpenAIEmbeddingProvider),
        ("bge", LocalBGEEmbeddingProvider),
    ):
        monkeypatch.setenv("EMBEDDING_PROVIDER", value)
        get_settings.cache_clear()
        build_embedding_provider.cache_clear()
        assert isinstance(build_embedding_provider(), expected)

    get_settings.cache_clear()
    build_embedding_provider.cache_clear()
