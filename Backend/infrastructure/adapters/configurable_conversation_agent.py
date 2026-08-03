from __future__ import annotations

from typing import Iterator

from domain.agents.conversation import (
    BaseDebuggableConversationAgent,
    ConversationAgentDefinition,
    ConversationAgentState,
)
from domain.agents.friend_events import FriendStreamEvent
from domain.agents.friend_runtime import FriendRuntime
from services.friend_service import FriendService


class ConfigurableConversationAgent(BaseDebuggableConversationAgent):
    def __init__(
        self,
        *,
        definition: ConversationAgentDefinition,
        runtime: FriendRuntime,
    ) -> None:
        self._definition = definition
        self._service = FriendService(runtime=runtime, definition=definition)

    @property
    def definition(self) -> ConversationAgentDefinition:
        return self._definition

    def get_state(self) -> ConversationAgentState:
        return ConversationAgentState(
            affinity=self._service.affinity,
            history=self._service.history,
        )

    def reset(self) -> None:
        self._service.reset()

    def force_next_cooldown(self) -> None:
        self._service.force_next_cooldown()

    def force_next_double_text(self) -> None:
        self._service.force_next_double_text()

    def end_cooldown(self) -> None:
        self._service.end_cooldown()

    def stream_reply(self, user_message: str) -> Iterator[FriendStreamEvent]:
        yield from self._service.stream_reply(user_message)
