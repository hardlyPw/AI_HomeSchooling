from __future__ import annotations

from typing import Iterator

from domain.agents.base import StreamEvent
from domain.agents.conversation import BaseDebuggableConversationAgent
from services.friend_service import FriendService


class JihoLegacyAdapter(BaseDebuggableConversationAgent):
    """Adapter around the existing AI_Friend-backed FriendService."""

    def __init__(self) -> None:
        self._service = FriendService()

    @property
    def agent_id(self) -> str:
        return "jiho"

    @property
    def display_name(self) -> str:
        return "Jiho"

    @property
    def affinity(self) -> int:
        return self._service.affinity

    @property
    def history(self) -> list[dict]:
        return self._service.history

    def reset(self) -> None:
        self._service.reset()

    def force_next_cooldown(self) -> None:
        self._service.force_next_cooldown()

    def force_next_double_text(self) -> None:
        self._service.force_next_double_text()

    def end_cooldown(self) -> None:
        self._service.end_cooldown()

    def stream_reply(self, user_message: str) -> Iterator[StreamEvent]:
        yield from self._service.stream_reply(user_message)
