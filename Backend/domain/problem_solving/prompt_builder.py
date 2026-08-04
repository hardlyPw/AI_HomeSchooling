from __future__ import annotations

from typing import Protocol

from domain.problem_solving.answer_judge import AnswerStatus


class ProblemPromptBuilder(Protocol):
    def opener(self, problem_sources: list[str]) -> str:
        raise NotImplementedError

    def reply(
        self,
        user_message: str,
        answer_status: AnswerStatus,
        problem_sources: list[str] | None,
    ) -> str:
        raise NotImplementedError
