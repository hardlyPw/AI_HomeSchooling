from __future__ import annotations

from collections.abc import Iterator
from types import ModuleType


class AIFriendResponseGenerator:
    """Response-generation gateway for the legacy AI_Friend module."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    @property
    def last_response_usage(self) -> dict | None:
        return getattr(self._module, "last_response_usage", None)

    def generate_response(self, prompt: str) -> str:
        return self._module.generate_ai_response(prompt)

    def split_double_text(self, response: str) -> list[str]:
        return self._module._split_double_text(response)

    def stream_response(self, prompt: str) -> Iterator:
        return self._module.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
            stream=True,
            stream_options={"include_usage": True},
        )
