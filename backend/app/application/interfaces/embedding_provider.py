"""EmbeddingProvider port — turns text into vectors.

The application depends on this abstraction; concrete providers (OpenAI, a local
BGE model, a deterministic dev provider) live in infrastructure and are selected
by configuration. Methods are async because real providers do network or
compute-bound work.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EmbeddingProvider(ABC):
    """Generates embedding vectors for text."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Stable identifier of the embedding model (for versioning)."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Dimensionality of the produced vectors."""

    @abstractmethod
    async def embed_text(self, text: str) -> list[float]:
        """Embed a single piece of text."""

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts at once (providers may batch for efficiency)."""

    async def health_check(self) -> bool:
        """Report whether the provider is usable. Override per provider."""
        return True
