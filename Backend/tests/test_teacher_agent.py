from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.prompts.lesson_prompt_builder import LessonPromptBuilder
from infrastructure.adapters.teacher_agent import TeacherAgent
from infrastructure.repositories.file_lesson_transcript_repository import (
    FileLessonTranscriptRepository,
)


class FakeTranscriptRepository:
    def context_through(self, current_video_time: float | None) -> str | None:
        return "[00:10] Exponents multiply repeated factors."


class FakeTutorClient:
    def __init__(self) -> None:
        self.messages: list[dict] = []

    def stream_reply(self, messages: list[dict]):
        self.messages = messages
        yield "First"
        yield " answer"


class TeacherAgentTest(unittest.TestCase):
    def test_file_repository_parses_and_filters_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "script.txt"
            path.write_text(
                "00:05\nIntroduction\n00:12\nExponent rule\ncontinued\n",
                encoding="utf-8",
            )
            repository = FileLessonTranscriptRepository(path)

            self.assertEqual(repository.context_through(4), None)
            self.assertEqual(repository.context_through(8), "[00:05] Introduction")
            self.assertEqual(
                repository.context_through(20),
                "[00:05] Introduction\n\n[00:12] Exponent rule continued",
            )

    def test_teacher_agent_composes_context_and_streams_client_reply(self) -> None:
        client = FakeTutorClient()
        agent = TeacherAgent(
            transcript_repository=FakeTranscriptRepository(),
            prompt_builder=LessonPromptBuilder(),
            tutor_client=client,
        )

        reply = "".join(agent.stream_reply(
            "Explain this figure.",
            conversation_history=[{"role": "user", "text": "Earlier question"}],
            current_video_time=30,
            figure_images=["data:image/png;base64,abc"],
        ))

        self.assertEqual(reply, "First answer")
        self.assertIn("Lesson transcript so far", client.messages[0]["content"])
        self.assertEqual(client.messages[-1]["content"][0]["text"], "Explain this figure.")
        self.assertEqual(
            client.messages[-1]["content"][1]["image_url"]["url"],
            "data:image/png;base64,abc",
        )


if __name__ == "__main__":
    unittest.main()
