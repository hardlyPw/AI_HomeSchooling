from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProblemSolvingSession:
    current_problem: int = 1
    total_problems: int = 1
    problem_labels: list[str] = field(default_factory=list)
    problem_stance: dict[int, int] = field(default_factory=dict)
    problem_turn_count: dict[int, int] = field(default_factory=dict)
    problem_conversations: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
    problem_strategy: dict[int, str] = field(default_factory=dict)
    session_memory: list[dict[str, Any]] = field(default_factory=list)

    def to_snapshot(self) -> dict[str, Any]:
        return copy.deepcopy({
            "current_problem": self.current_problem,
            "total_problems": self.total_problems,
            "problem_labels": self.problem_labels,
            "problem_stance": self.problem_stance,
            "problem_turn_count": self.problem_turn_count,
            "problem_conversations": self.problem_conversations,
            "problem_strategy": self.problem_strategy,
            "session_memory": self.session_memory,
        })

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "ProblemSolvingSession":
        return cls(
            current_problem=int(snapshot["current_problem"]),
            total_problems=int(snapshot["total_problems"]),
            problem_labels=list(snapshot["problem_labels"]),
            problem_stance=dict(snapshot["problem_stance"]),
            problem_turn_count=dict(snapshot["problem_turn_count"]),
            problem_conversations=copy.deepcopy(snapshot["problem_conversations"]),
            problem_strategy=dict(snapshot["problem_strategy"]),
            session_memory=copy.deepcopy(snapshot["session_memory"]),
        )
