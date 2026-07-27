from __future__ import annotations

from typing import Iterator

from AI_Teacher import get_teacher_response_stream
from domain.agents.lesson import BaseLessonAgent


class TeacherLegacyAdapter(BaseLessonAgent):
    """Adapter around the existing AI_Teacher module."""

    @property
    def agent_id(self) -> str:
        return "lesson-teacher"

    @property
    def display_name(self) -> str:
        return "Teacher"

    def reset(self) -> None:
        return None

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
