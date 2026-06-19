"""Embedding provider factory — selects the provider from configuration.

``EMBEDDING_PROVIDER`` chooses the implementation:
  * ``hash``           -> DeterministicEmbeddingProvider (offline dev/test default)
  * ``openai``         -> OpenAIEmbeddingProvider
  * ``bge`` / ``local``-> LocalBGEEmbeddingProvider

Cached as a process-wide singleton; call ``build_embedding_provider.cache_clear()``
in tests that change configuration.
"""

from __future__ import annotations

from functools import lru_cache

from app.application.interfaces.embedding_provider import EmbeddingProvider
from app.core.config import get_settings
from app.infrastructure.embeddings.bge_provider import LocalBGEEmbeddingProvider
from app.infrastructure.embeddings.deterministic_provider import DeterministicEmbeddingProvider
from app.infrastructure.embeddings.openai_provider import OpenAIEmbeddingProvider


@lru_cache(maxsize=1)
def build_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    kind = settings.embedding_provider.lower()

    if kind == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model=settings.embedding_model,
            dimensions=settings.embedding_dimensions,
        )
    if kind in ("bge", "local"):
        return LocalBGEEmbeddingProvider(dimensions=settings.embedding_dimensions)
    return DeterministicEmbeddingProvider(dimensions=settings.embedding_dimensions)
