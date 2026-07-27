from __future__ import annotations

from abc import abstractmethod
from typing import Iterator

from domain.agents.base import BaseAgent, StreamEvent


class BaseConversationAgent(BaseAgent):
    """Base class for free-form character conversation agents."""

    @property
    @abstractmethod
    def affinity(self) -> int:
        raise NotImplementedError

    @property
    @abstractmethod
    def history(self) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def stream_reply(self, user_message: str) -> Iterator[StreamEvent]:
        raise NotImplementedError


class BaseDebuggableConversationAgent(BaseConversationAgent):
    """Optional debug controls for character agents used by developer UI."""

    @abstractmethod
    def force_next_cooldown(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def force_next_double_text(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def end_cooldown(self) -> None:
        raise NotImplementedError
