from __future__ import annotations

from typing import Iterator

from domain.agents.base import StreamEvent
from domain.agents.conversation import (
    BaseDebuggableConversationAgent,
    ConversationAgentProfile,
    ConversationAgentState,
    ConversationBehaviorConfig,
)
from domain.agents.jiho import JIHO_BEHAVIOR, JIHO_PROFILE
from services.friend_service import FriendService


class JihoLegacyAdapter(BaseDebuggableConversationAgent):
    """Adapter around the existing AI_Friend-backed FriendService."""

    def __init__(self) -> None:
        self._service = FriendService()

    @property
    def profile(self) -> ConversationAgentProfile:
        return JIHO_PROFILE

    @property
    def behavior(self) -> ConversationBehaviorConfig:
        return JIHO_BEHAVIOR

    def get_state(self) -> ConversationAgentState:
        return ConversationAgentState(
            affinity=self._service.affinity,
            history=self._service.history,
            away_count=getattr(self._service, "_away_count", 0),
        )

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
