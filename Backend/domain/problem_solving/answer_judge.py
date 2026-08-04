from __future__ import annotations

from enum import Enum
from typing import Protocol


class AnswerStatus(str, Enum):
    SOLVED = "SOLVED"
    INCORRECT = "INCORRECT"
    UNCLEAR = "UNCLEAR"

    @classmethod
    def from_value(cls, value: str) -> "AnswerStatus":
        try:
            return cls(value.upper())
        except ValueError:
            return cls.UNCLEAR


class AnswerJudge(Protocol):
    def assess(self, user_message: str, problem_sources: list[str] | None) -> AnswerStatus:
        raise NotImplementedError

    def solved_reply(
        self,
        user_message: str,
        is_last_problem: bool,
        problem_sources: list[str] | None,
    ) -> str:
        raise NotImplementedError
