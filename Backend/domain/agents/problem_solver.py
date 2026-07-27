from __future__ import annotations

from abc import abstractmethod

from domain.agents.base import BaseAgent
from domain.problem_solving.autorater import AutoraterChatResult, AutoraterStartResult


class BaseProblemSolverAgent(BaseAgent):
    """Base class for agents that run a problem-solving session."""

    @abstractmethod
    def start_session(self, problem_sources: list[str]) -> AutoraterStartResult:
        raise NotImplementedError

    @abstractmethod
    def reply(self, message: str, problem_sources: list[str] | None = None) -> AutoraterChatResult:
        raise NotImplementedError

    @abstractmethod
    def get_progress(self) -> dict:
        raise NotImplementedError
