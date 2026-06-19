"""AnthropicProvider — LLMProvider backed by the Anthropic Messages API.

The SDK is imported lazily so the dependency is only required when this provider
is actually selected. Structured output is requested as JSON and parsed.
"""

from __future__ import annotations

import json
from typing import Any

from app.application.interfaces.llm_provider import LLMProvider

_DEFAULT_MAX_TOKENS = 1024


class AnthropicProvider(LLMProvider):
    def __init__(self, *, api_key: str | None, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client  # injectable for tests

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self) -> Any:
        if self._client is None:
            from anthropic import AsyncAnthropic  # lazy import

            self._client = AsyncAnthropic(api_key=self._api_key)
        return self._client

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        resp = await self._get_client().messages.create(
            model=self._model,
            max_tokens=_DEFAULT_MAX_TOKENS,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text if resp.content else ""

    async def structured_generate(
        self, prompt: str, *, schema: dict[str, str], system: str | None = None
    ) -> dict[str, Any]:
        instruction = (
            "Respond ONLY with a JSON object having exactly these keys and types: "
            + ", ".join(f"{k} ({v})" for k, v in schema.items())
        )
        full_system = f"{system}\n{instruction}" if system else instruction
        raw = await self.generate(prompt, system=full_system)
        try:
            data = json.loads(raw)
            return {key: data.get(key) for key in schema}
        except (json.JSONDecodeError, AttributeError):
            return {key: None for key in schema}

    async def health_check(self) -> bool:
        return bool(self._api_key)
