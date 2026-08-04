from __future__ import annotations

from collections.abc import Iterator

from application.prompts.lesson_prompt_builder import LessonPromptBuilder
from domain.agents.lesson import BaseLessonAgent
from domain.lesson.transcript import LessonTranscriptRepository
from domain.lesson.tutor import LessonTutorClient


class TeacherAgent(BaseLessonAgent):
    def __init__(
        self,
        transcript_repository: LessonTranscriptRepository,
        prompt_builder: LessonPromptBuilder,
        tutor_client: LessonTutorClient,
    ) -> None:
        self._transcript_repository = transcript_repository
        self._prompt_builder = prompt_builder
        self._tutor_client = tutor_client

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
        transcript_context = self._transcript_repository.context_through(
            current_video_time
        )
        messages = self._prompt_builder.build_messages(
            user_message=user_message,
            conversation_history=conversation_history,
            transcript_context=transcript_context,
            figure_images=figure_images,
        )
        yield from self._tutor_client.stream_reply(messages)
