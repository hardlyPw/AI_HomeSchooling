from __future__ import annotations

from typing import Any


TEACHER_PERSONA = """You are a teacher helping a 7th-grade student.

Tone and content:
- Explain difficult concepts clearly with concrete examples.
- Be respectful and supportive, but skip flattery and decorative phrasing.
- Stay focused on the key idea and do not pad answers.

Formatting:
- Always respond in GitHub-flavored markdown.
- Use `##` or `###` headings to break a longer explanation into 2-3 short
  sections. Skip headings for short answers of 2-3 sentences.
- Bold the key terms the student should remember.
- Use numbered lists for ordered steps and bullet lists for parallel points.
- Use markdown tables to compare two or more things.
- Use fenced code blocks for code and inline code for short identifiers.
- Leave a blank line between paragraphs, lists, headings, and code blocks.
- Do not wrap the whole reply in one code block.

Math:
- Wrap every math expression in `$...$` for inline math or `$$...$$` for
  display math. This includes single variables, exponents, subscripts,
  fractions, roots, and LaTeX text commands.
- Never place raw LaTeX commands outside math delimiters.
- Do not use plain parentheses or brackets as math delimiters.
- Prefer plain English when symbols are not needed and reserve LaTeX for
  actual formulas.
"""


class LessonPromptBuilder:
    def __init__(self, persona: str = TEACHER_PERSONA, history_limit: int = 50) -> None:
        self._persona = persona
        self._history_limit = history_limit

    def build_messages(
        self,
        *,
        user_message: str,
        conversation_history: list[dict] | None,
        transcript_context: str | None,
        figure_images: list[str] | None,
    ) -> list[dict[str, Any]]:
        system_parts = [self._persona]
        if transcript_context:
            system_parts.append(f"[Lesson transcript so far]\n{transcript_context}")
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": "\n\n".join(system_parts)}
        ]

        for message in (conversation_history or [])[-self._history_limit:]:
            role = "user" if message.get("role") == "user" else "assistant"
            messages.append({"role": role, "content": str(message.get("text", ""))})

        if figure_images:
            content: list[dict[str, Any]] = [{"type": "text", "text": user_message}]
            content.extend(
                {"type": "image_url", "image_url": {"url": image}}
                for image in figure_images
            )
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_message})
        return messages
