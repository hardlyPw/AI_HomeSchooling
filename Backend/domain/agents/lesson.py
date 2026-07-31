from __future__ import annotations

from abc import abstractmethod
from typing import Iterator

from domain.agents.base import BaseAgent


class BaseLessonAgent(BaseAgent):
    """Base class for agents that tutor around lesson context."""

    @abstractmethod
    def stream_reply(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
        current_video_time: float | None = None,
        figure_images: list[str] | None = None,
    ) -> Iterator[str]:
        raise NotImplementedError
