from __future__ import annotations

from typing import Iterator

from AI_Teacher import get_teacher_response_stream


class TeacherLegacyAdapter:
    """Adapter around the existing AI_Teacher module."""

    def stream_reply(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
        current_video_time: float | None = None,
        figure_images: list[str] | None = None,
    ) -> Iterator[str]:
        yield from get_teacher_response_stream(
            user_message,
            conversation_history,
            current_video_time,
            figure_images,
        )
