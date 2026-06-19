"""LLMProvider port — text and structured generation behind an abstraction.

The application/workflow layer depends on this port, never on a concrete SDK.
Implementations live in ``infrastructure/llm/providers`` and are selected by
configuration (mirroring the embedding provider). A deterministic, offline
implementation backs dev and tests so the workflow runs without API keys.

``structured_generate`` takes a ``schema`` mapping the expected output keys to a
short type hint (e.g. ``{"candidates": "list[str]"}`` or ``{"memory_type":
"str"}``) and returns a dict honoring those keys — keeping callers free of any
SDK-specific structured-output mechanism.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class LLMProvider(ABC):
    @property
    @abstractmethod
    def model_name(self) -> str: ...

    @abstractmethod
    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        """Return a free-text completion for the prompt."""

    @abstractmethod
    async def structured_generate(
        self, prompt: str, *, schema: dict[str, str], system: str | None = None
    ) -> dict[str, Any]:
        """Return a dict honoring the requested ``schema`` keys."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Cheap readiness probe; must never raise."""
