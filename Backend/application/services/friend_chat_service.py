from __future__ import annotations

from typing import Iterator

from domain.agents.conversation import BaseDebuggableConversationAgent
from domain.agents.friend_events import FriendStreamEvent


class FriendChatService:
    def __init__(self, agent: BaseDebuggableConversationAgent) -> None:
        self._agent = agent

    @property
    def affinity(self) -> int:
        return self._agent.affinity

    @property
    def history(self) -> list[dict]:
        return self._agent.history

    @property
    def message_count(self) -> int:
        return len(self.history) // 2

    def reset(self) -> int:
        self._agent.reset()
        return self.affinity

    def force_next_cooldown(self) -> None:
        self._agent.force_next_cooldown()

    def force_next_double_text(self) -> None:
        self._agent.force_next_double_text()

    def end_cooldown(self) -> None:
        self._agent.end_cooldown()

    def stream_reply(self, user_message: str) -> Iterator[FriendStreamEvent]:
        yield from self._agent.stream_reply(user_message)
