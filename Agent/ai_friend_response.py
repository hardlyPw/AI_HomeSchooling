from __future__ import annotations

import sys
import time
from pathlib import Path


_BACKEND_DIR = Path(__file__).resolve().parents[1] / "Backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from domain.agents.jiho import JIHO_DEFINITION  # noqa: E402


def generate_response(openai_client, prompt_text: str) -> tuple[str, dict | None]:
    """Generate Jiho's final text response and return token usage metadata."""

    print("\nGPT 답변 생성 중...")
    start = time.time()
    model_config = JIHO_DEFINITION.runtime.response_model
    response = openai_client.chat.completions.create(
        model=model_config.model,
        messages=[{"role": "system", "content": prompt_text}],
        temperature=model_config.temperature,
        max_tokens=model_config.max_tokens,
    )
    print(f"[Latency] GPT 답변: {time.time() - start:.4f}초")

    usage = (
        {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }
        if getattr(response, "usage", None) is not None
        else None
    )
    return response.choices[0].message.content or "brb, gimme a sec", usage


def split_double_text(text: str) -> list[str]:
    """Split one response into at most two short chat beats."""

    parts = [part.strip() for part in text.split(".") if part.strip()]
    if len(parts) >= 2:
        return [parts[0], ". ".join(parts[1:])]

    words = text.split()
    if len(words) >= 4:
        mid = len(words) // 2
        return [" ".join(words[:mid]), " ".join(words[mid:])]

    return [text]
