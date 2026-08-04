from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class OpenAILessonTutorClient:
    def __init__(
        self,
        openai_client,
        *,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 800,
    ) -> None:
        self._client = openai_client
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    def stream_reply(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        stream = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
