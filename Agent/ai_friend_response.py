from __future__ import annotations

import time


def generate_response(openai_client, prompt_text: str) -> tuple[str, dict | None]:
    """Generate Jiho's final text response and return token usage metadata."""

    print("\nGPT 답변 생성 중...")
    start = time.time()
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_text}],
        temperature=0.8,
        max_tokens=300,
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
