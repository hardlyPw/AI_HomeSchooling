from AI_Teacher import get_teacher_response

HISTORY_LIMIT = 50  # 최대 50개 메시지 유지 (25회 대화)

class ChatService:
    def __init__(self):
        self.conversation_history: list[dict] = []

    def get_reply(
        self,
        user_message: str,
        pdf_context: str | None = None,
        figure_context: str | None = None,
        figure_image: str | None = None,
        current_video_time: float | None = None,
    ) -> tuple[str, str]:
        parts: list[str] = []
        if pdf_context:
            parts.append(
                f'I highlighted this passage from the textbook:\n"""\n{pdf_context}\n"""'
            )
        if figure_context:
            parts.append(f'I clicked on a figure in the textbook. {figure_context}')
        if figure_image:
            parts.append('The clicked figure is attached as an image.')

        if parts:
            user_content = "\n\n".join(parts) + f"\n\nMy question: {user_message}"
        else:
            user_content = user_message

        reply, summary = get_teacher_response(
            user_content,
            self.conversation_history,
            current_video_time,
            figure_image,
        )

        self.conversation_history.append({"role": "user", "text": user_content})
        self.conversation_history.append({"role": "assistant", "text": reply})

        if len(self.conversation_history) > HISTORY_LIMIT:
            self.conversation_history = self.conversation_history[-HISTORY_LIMIT:]

        return reply, summary
