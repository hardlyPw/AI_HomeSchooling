from __future__ import annotations

import threading

from domain.agents.conversation import ConversationAgentDefinition


class InMemoryConversationAgentRepository:
    """Thread-safe process-local Agent catalog for the first creation flow."""

    def __init__(
        self,
        initial_definitions: tuple[ConversationAgentDefinition, ...] = (),
    ) -> None:
        self._definitions = {
            definition.profile.agent_id: definition
            for definition in initial_definitions
        }
        self._lock = threading.RLock()

    def list_all(self) -> list[ConversationAgentDefinition]:
        with self._lock:
            return list(self._definitions.values())

    def get(self, agent_id: str) -> ConversationAgentDefinition | None:
        with self._lock:
            return self._definitions.get(agent_id)

    def save(self, definition: ConversationAgentDefinition) -> None:
        with self._lock:
            self._definitions[definition.profile.agent_id] = definition
