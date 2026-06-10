import os
import re
from typing import Iterator
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "data", "script_new.txt")

TEACHER_PERSONA = """You are a teacher helping a 7th-grade student.

Tone & content:
- Explain difficult concepts in a clear, friendly way with concrete examples.
- Be respectful and supportive, but skip flattery and decorative phrasing.
- Stay focused on the key idea; do not pad answers.

Formatting (always respond in GitHub-flavored markdown):
- Use `##` or `###` headings to break a longer explanation into 2–4 short sections. Skip headings for short answers (≤3 sentences).
- **Bold** the key terms the student should remember.
- Use numbered lists for ordered steps, bullet lists for parallel points.
- Use markdown tables to compare two or more things.
- Use fenced code blocks (```lang) for code; use inline `code` for short identifiers.
- Leave a blank line between paragraphs, lists, headings, and code blocks so they render cleanly.
- Do NOT wrap the whole reply in a single code block.

Math (STRICT — the renderer only understands `$...$` and `$$...$$`):
- Wrap EVERY math expression in `$...$` (inline) or `$$...$$` (display). This includes single variables like $x$, $a$, $n$, exponents like $a^x$, subscripts like $x_1$, fractions $\\frac{a}{b}$, roots $\\sqrt{2}$, and any `\\text{...}`, `\\frac{...}`, etc.
- NEVER write raw LaTeX commands (`\\text`, `\\frac`, `\\sqrt`, `^{...}`, `_{...}`) outside of `$` delimiters. They will render as broken plain text (the backslash even shows as `₩` on Korean systems).
- NEVER use parentheses `( ... )` or square brackets `[ ... ]` to denote math. Use `$...$` instead. Example: write `$a^x$`, NOT `( a^x )`.
- Prefer plain English when symbols are not needed. Write "a raised to a rational power" instead of `$a^{\\text{rational}}$`. Reserve LaTeX for actual formulas, not as decorative labels.
- For display equations on their own line, use `$$...$$` with blank lines above and below.
"""


def _parse_script(filepath: str) -> list[dict]:
    """script.txt → [{ts_seconds, ts_label, content}, ...]"""
    ts_pattern = re.compile(r'^(\d{1,2}):(\d{2})\s*$')
    sections: list[dict] = []
    current_label: str | None = None
    current_seconds: int = 0
    current_text: list[str] = []

    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            m = ts_pattern.match(stripped)
            if m:
                if current_label is not None and current_text:
                    sections.append({
                        "ts_seconds": current_seconds,
                        "ts_label": current_label,
                        "content": " ".join(current_text).strip(),
                    })
                current_label = stripped
                current_seconds = int(m.group(1)) * 60 + int(m.group(2))
                current_text = []
            elif stripped and current_label is not None:
                current_text.append(stripped)

    if current_label is not None and current_text:
        sections.append({
            "ts_seconds": current_seconds,
            "ts_label": current_label,
            "content": " ".join(current_text).strip(),
        })

    return sections


_SCRIPT_CACHE: list[dict] | None = None


def _get_script() -> list[dict]:
    global _SCRIPT_CACHE
    if _SCRIPT_CACHE is None:
        _SCRIPT_CACHE = _parse_script(SCRIPT_PATH)
        print(f"[AI_Teacher] script.txt 로드: {len(_SCRIPT_CACHE)}개 청크")
    return _SCRIPT_CACHE


def get_script_so_far(current_video_time: float | None) -> str | None:
    """영상 currentTime 이하 타임스탬프의 청크를 모두 합쳐서 반환."""
    if current_video_time is None or current_video_time <= 0:
        return None
    sections = _get_script()
    visible = [s for s in sections if s["ts_seconds"] <= current_video_time]
    if not visible:
        return None
    return "\n\n".join(f"[{s['ts_label']}] {s['content']}" for s in visible)


def _log_prompt(messages: list[dict]) -> None:
    SEP = "─" * 60
    print(f"\n{SEP}")
    print("📋 [PROMPT DEBUG]")
    print(SEP)
    for i, msg in enumerate(messages):
        role_label = {"system": "🔧 SYSTEM", "user": "🙋 USER", "assistant": "🤖 ASSISTANT"}.get(msg["role"], msg["role"].upper())
        content = msg["content"]
        if isinstance(content, list):
            text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
            image_count = sum(1 for c in content if c.get("type") == "image_url")
            content = "\n".join(text_parts) + (f"\n[+{image_count} image(s)]" if image_count else "")
        print(f"[{i}] {role_label}\n{content}")
        print(SEP)
    print()


def get_teacher_response(
    user_message: str,
    conversation_history: list[dict] | None = None,
    current_video_time: float | None = None,
    figure_images: list[str] | None = None,
) -> tuple[str, str]:
    script_context = get_script_so_far(current_video_time)
    print(f"[DEBUG] 영상 시간:        {f'{current_video_time:.1f}s' if current_video_time is not None else '없음'}")
    print(f"[DEBUG] 스크립트 컨텍스트: {'포함 (' + str(len(script_context)) + '자)' if script_context else '없음 (수업 전)'}")
    print(f"[DEBUG] 대화 히스토리:    {len(conversation_history) if conversation_history else 0}개")
    print(f"[DEBUG] Figure 이미지:    {'첨부 ' + str(len(figure_images)) + '장' if figure_images else '없음'}")

    system_parts = [TEACHER_PERSONA]
    if script_context:
        system_parts.append(f"[Lesson transcript so far]\n{script_context}")
    system_prompt = "\n\n".join(system_parts)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        for msg in conversation_history[-50:]:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["text"]})

    if figure_images:
        content_parts: list[dict] = [{"type": "text", "text": user_message}]
        for img in figure_images:
            content_parts.append({"type": "image_url", "image_url": {"url": img}})
        messages.append({"role": "user", "content": content_parts})
    else:
        messages.append({"role": "user", "content": user_message})

    _log_prompt(messages)

    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=500,
    )
    reply = response.choices[0].message.content or "Please try asking again in a moment."
    summary = _summarize(reply)
    return reply, summary


def get_teacher_response_stream(
    user_message: str,
    conversation_history: list[dict] | None = None,
    current_video_time: float | None = None,
    figure_images: list[str] | None = None,
) -> Iterator[str]:
    """Stream the teacher's reply token-by-token. Yields content deltas only."""
    script_context = get_script_so_far(current_video_time)
    print(f"[DEBUG/stream] 영상 시간:        {f'{current_video_time:.1f}s' if current_video_time is not None else '없음'}")
    print(f"[DEBUG/stream] 스크립트 컨텍스트: {'포함 (' + str(len(script_context)) + '자)' if script_context else '없음 (수업 전)'}")
    print(f"[DEBUG/stream] 대화 히스토리:    {len(conversation_history) if conversation_history else 0}개")
    print(f"[DEBUG/stream] Figure 이미지:    {'첨부 ' + str(len(figure_images)) + '장' if figure_images else '없음'}")

    system_parts = [TEACHER_PERSONA]
    if script_context:
        system_parts.append(f"[Lesson transcript so far]\n{script_context}")
    system_prompt = "\n\n".join(system_parts)

    messages: list[dict] = [{"role": "system", "content": system_prompt}]

    if conversation_history:
        for msg in conversation_history[-50:]:
            role = "user" if msg["role"] == "user" else "assistant"
            messages.append({"role": role, "content": msg["text"]})

    if figure_images:
        content_parts: list[dict] = [{"type": "text", "text": user_message}]
        for img in figure_images:
            content_parts.append({"type": "image_url", "image_url": {"url": img}})
        messages.append({"role": "user", "content": content_parts})
    else:
        messages.append({"role": "user", "content": user_message})

    _log_prompt(messages)

    stream = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        temperature=0.7,
        max_tokens=800,
        stream=True,
    )
    for chunk in stream:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def summarize_reply(answer: str) -> str:
    return _summarize(answer)


def _summarize(answer: str) -> str:
    response = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": (
                "Summarize the teacher's answer in 2-3 short sentences a student can quickly read in chat. "
                "Keep only the core concept. "
                "No filler or decorative phrasing."
            )},
            {"role": "user", "content": answer},
        ],
        temperature=0.3,
        max_tokens=150,
    )
    return response.choices[0].message.content or answer
