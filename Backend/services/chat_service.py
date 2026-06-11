from typing import Iterator
from AI_Teacher import get_teacher_response, get_teacher_response_stream

HISTORY_LIMIT = 50  # 최대 50개 메시지 유지 (25회 대화)

class ChatService:
    def __init__(self):
        self.conversation_history: list[dict] = []

    def _build_user_content(
        self,
        user_message: str,
        pdf_context: str | None,
        figure_context: str | None,
        figure_images: list[str] | None,
    ) -> str:
        parts: list[str] = []
        if pdf_context:
            parts.append(
                f'I highlighted this passage from the textbook:\n"""\n{pdf_context}\n"""'
            )
        if figure_context:
            parts.append(f'I clicked on a figure in the textbook. {figure_context}')
        if figure_images:
            n = len(figure_images)
            noun = 'image' if n == 1 else 'images'
            parts.append(f'I attached {n} selected {noun} for you to use when answering.')

        if parts:
            return "\n\n".join(parts) + f"\n\nMy question: {user_message}"
        return user_message

    def _record_turn(self, user_content: str, reply: str) -> None:
        self.conversation_history.append({"role": "user", "text": user_content})
        self.conversation_history.append({"role": "assistant", "text": reply})
        if len(self.conversation_history) > HISTORY_LIMIT:
            self.conversation_history = self.conversation_history[-HISTORY_LIMIT:]

    def get_reply(
        self,
        user_message: str,
        pdf_context: str | None = None,
        figure_context: str | None = None,
        figure_images: list[str] | None = None,
        current_video_time: float | None = None,
    ) -> tuple[str, str]:
        user_content = self._build_user_content(user_message, pdf_context, figure_context, figure_images)

        reply, summary = get_teacher_response(
            user_content,
            self.conversation_history,
            current_video_time,
            figure_images,
        )

        self._record_turn(user_content, reply)
        return reply, summary

    def get_reply_stream(
        self,
        user_message: str,
        pdf_context: str | None = None,
        figure_context: str | None = None,
        figure_images: list[str] | None = None,
        current_video_time: float | None = None,
    ) -> Iterator[str]:
        user_content = self._build_user_content(user_message, pdf_context, figure_context, figure_images)

        collected: list[str] = []
        for delta in get_teacher_response_stream(
            user_content,
            self.conversation_history,
            current_video_time,
            figure_images,
        ):
            collected.append(delta)
            yield delta

        reply = "".join(collected) or "Please try asking again in a moment."
        self._record_turn(user_content, reply)
