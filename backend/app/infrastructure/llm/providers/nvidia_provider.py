"""NvidiaProvider — LLMProvider backed by NVIDIA NIM via ChatNVIDIA.

Uses ``langchain_nvidia_ai_endpoints.ChatNVIDIA`` (a LangChain chat model). The
package is imported lazily so the dependency is only required when this provider
is actually selected (the offline default is deterministic). Credentials come
only from configuration (``NVIDIA_API_KEY``) and the model from ``LLM_MODEL`` —
nothing is hardcoded. Structured output is requested as JSON and parsed, matching
the OpenAI and Anthropic adapters.
"""

from __future__ import annotations

import json
from typing import Any


from app.application.interfaces.llm_provider import LLMProvider


class NvidiaProvider(LLMProvider):
    def __init__(self, *, api_key: str | None, model: str, client: Any | None = None) -> None:
        self._api_key = api_key
        self._model = model
        self._client = client  # injectable for tests (a ChatNVIDIA-like object)

    @property
    def model_name(self) -> str:
        return self._model

    def _get_client(self) -> Any:
        if self._client is None:
            from langchain_nvidia_ai_endpoints import ChatNVIDIA  # lazy import

            self._client = ChatNVIDIA(model=self._model, api_key=self._api_key)
        return self._client

    async def generate(self, prompt: str, *, system: str | None = None) -> str:
        # ChatNVIDIA accepts LangChain (role, content) tuples; avoids importing
        # message classes. ainvoke returns a message whose .content is the text.
        messages: list[tuple[str, str]] = []
        if system:
            messages.append(("system", system))
        messages.append(("human", prompt))
        resp = await self._get_client().ainvoke(messages)
        content = getattr(resp, "content", "")
        return content if isinstance(content, str) else str(content)

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
