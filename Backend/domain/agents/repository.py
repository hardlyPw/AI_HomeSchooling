from __future__ import annotations

from typing import Protocol

from domain.agents.conversation import ConversationAgentDefinition


class ConversationAgentRepository(Protocol):
    def list_all(self) -> list[ConversationAgentDefinition]:
        raise NotImplementedError

    def get(self, agent_id: str) -> ConversationAgentDefinition | None:
        raise NotImplementedError

    def save(self, definition: ConversationAgentDefinition) -> None:
        raise NotImplementedError

    def delete(self, agent_id: str) -> bool:
        raise NotImplementedError
