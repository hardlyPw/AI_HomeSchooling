from __future__ import annotations

from collections.abc import Iterator
import sys
from pathlib import Path
from types import ModuleType

AGENT_DIR = Path(__file__).resolve().parents[3] / "Agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from ai_friend_response import generate_response as generate_jiho_response
from ai_friend_response import split_double_text
from domain.agents.jiho import JIHO_DEFINITION


class AIFriendResponseGenerator:
    """Response-generation gateway backed by extracted Jiho helpers when available."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    @property
    def _state(self):
        return getattr(self._module, "runtime_state", None)

    @property
    def last_response_usage(self) -> dict | None:
        if self._state is not None:
            return getattr(self._state, "last_response_usage", None)
        return getattr(self._module, "last_response_usage", None)

    def generate_response(self, prompt: str) -> str:
        if self._state is not None:
            text, usage = generate_jiho_response(self._module.openai_client, prompt)
            self._state.last_response_usage = usage
            return text
        return self._module.generate_ai_response(prompt)

    def split_double_text(self, response: str) -> list[str]:
        if self._state is not None:
            return split_double_text(response)
        return self._module._split_double_text(response)

    def stream_response(self, prompt: str) -> Iterator:
        if self._state is not None:
            self._state.last_response_usage = None
        else:
            self._module.last_response_usage = None

        model_config = JIHO_DEFINITION.runtime.response_model
        stream = self._module.openai_client.chat.completions.create(
            model=model_config.model,
            messages=[{"role": "system", "content": prompt}],
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        for chunk in stream:
            usage = getattr(chunk, "usage", None)
            if usage is not None:
                usage_payload = {
                    "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens,
                }
                if self._state is not None:
                    self._state.last_response_usage = usage_payload
                else:
                    self._module.last_response_usage = usage_payload
            yield chunk
