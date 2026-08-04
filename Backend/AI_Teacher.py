"""Compatibility entry points for scripts that still import AI_Teacher."""

from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from application.prompts.lesson_prompt_builder import LessonPromptBuilder, TEACHER_PERSONA
from infrastructure.adapters.teacher_agent import TeacherAgent
from infrastructure.clients.openai_lesson_tutor_client import OpenAILessonTutorClient
from infrastructure.repositories.file_lesson_transcript_repository import (
    FileLessonTranscriptRepository,
)


SCRIPT_PATH = Path(__file__).resolve().parent / "data" / "script_new.txt"


@lru_cache(maxsize=1)
def _transcript_repository() -> FileLessonTranscriptRepository:
    return FileLessonTranscriptRepository(SCRIPT_PATH)


@lru_cache(maxsize=1)
def _teacher_agent() -> TeacherAgent:
    load_dotenv()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return TeacherAgent(
        transcript_repository=_transcript_repository(),
        prompt_builder=LessonPromptBuilder(),
        tutor_client=OpenAILessonTutorClient(client),
    )


def get_script_so_far(current_video_time: float | None) -> str | None:
    return _transcript_repository().context_through(current_video_time)


def get_teacher_response_stream(
    user_message: str,
    conversation_history: list[dict] | None = None,
    current_video_time: float | None = None,
    figure_images: list[str] | None = None,
) -> Iterator[str]:
    yield from _teacher_agent().stream_reply(
        user_message,
        conversation_history,
        current_video_time,
        figure_images,
    )


__all__ = [
    "SCRIPT_PATH",
    "TEACHER_PERSONA",
    "get_script_so_far",
    "get_teacher_response_stream",
]
