from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


StreamEvent = dict[str, Any]


class BaseAgent(ABC):
    """Common identity contract shared by every content agent."""

    @property
    @abstractmethod
    def agent_id(self) -> str:
        raise NotImplementedError

    @property
    @abstractmethod
    def display_name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError
