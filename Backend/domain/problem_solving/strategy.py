from __future__ import annotations

from enum import Enum
from typing import Protocol


class TeachingStrategy(str, Enum):
    SOCRATIC = "socratic"
    WORKED_EXAMPLE_FADING = "worked_example_fading"
    PROTEGE_EFFECT = "protege_effect"

    @classmethod
    def from_value(cls, value: str | None) -> "TeachingStrategy":
        try:
            return cls(value or cls.SOCRATIC.value)
        except ValueError:
            return cls.SOCRATIC


class TeachingStrategyPolicy(Protocol):
    def choose(self, problem_number: int, problem_sources: list[str]) -> TeachingStrategy:
        raise NotImplementedError

    def current(self) -> TeachingStrategy:
        raise NotImplementedError

    def display_name(self, strategy: TeachingStrategy) -> str:
        raise NotImplementedError
