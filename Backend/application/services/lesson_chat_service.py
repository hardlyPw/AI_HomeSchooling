from __future__ import annotations

from typing import Iterator

from domain.agents.base import LessonTutor
from domain.chat.messages import LessonChatInput


HISTORY_LIMIT = 50


class LessonChatService:
    def __init__(self, tutor: LessonTutor) -> None:
        self._tutor = tutor
        self._conversation_history: list[dict] = []

    def _build_user_content(self, lesson_input: LessonChatInput) -> str:
        parts: list[str] = []
        if lesson_input.pdf_context:
            parts.append(
                f'I highlighted this passage from the textbook:\n"""\n{lesson_input.pdf_context}\n"""'
            )
        if lesson_input.figure_context:
            parts.append(f'I clicked on a figure in the textbook. {lesson_input.figure_context}')
        if lesson_input.figure_images:
            n = len(lesson_input.figure_images)
            noun = 'image' if n == 1 else 'images'
            parts.append(f'I attached {n} selected {noun} for you to use when answering.')

        if parts:
            return "\n\n".join(parts) + f"\n\nMy question: {lesson_input.message}"
        return lesson_input.message

    def _record_turn(self, user_content: str, reply: str) -> None:
        self._conversation_history.append({"role": "user", "text": user_content})
        self._conversation_history.append({"role": "assistant", "text": reply})
        if len(self._conversation_history) > HISTORY_LIMIT:
            self._conversation_history = self._conversation_history[-HISTORY_LIMIT:]

    def get_reply_stream(self, lesson_input: LessonChatInput) -> Iterator[str]:
        user_content = self._build_user_content(lesson_input)

        collected: list[str] = []
        for delta in self._tutor.stream_reply(
            user_content,
            self._conversation_history,
            lesson_input.current_video_time,
            lesson_input.figure_images,
        ):
            collected.append(delta)
            yield delta

        reply = "".join(collected) or "Please try asking again in a moment."
        self._record_turn(user_content, reply)
