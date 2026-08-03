from __future__ import annotations

from collections.abc import Callable
import threading

from application.services.agent_catalog_service import AgentNotFoundError
from application.services.friend_chat_service import FriendChatService
from domain.agents.conversation import ConversationAgentDefinition
from domain.agents.repository import ConversationAgentRepository


AgentServiceFactory = Callable[
    [ConversationAgentDefinition, str],
    FriendChatService,
]


class AgentSessionRegistry:
    """Owns isolated chat services keyed by user, Agent, and browser session."""

    def __init__(
        self,
        repository: ConversationAgentRepository,
        service_factory: AgentServiceFactory,
    ) -> None:
        self._repository = repository
        self._service_factory = service_factory
        self._services: dict[tuple[str, str, str], FriendChatService] = {}
        self._lock = threading.RLock()

    def get(
        self,
        agent_id: str,
        session_id: str | None,
        user_id: str | None,
    ) -> FriendChatService:
        definition = self._repository.get(agent_id)
        if definition is None:
            raise AgentNotFoundError(agent_id)

        normalized_user = self._normalize(user_id, fallback="anonymous")
        normalized_session = self._normalize(session_id, fallback="default")
        key = (normalized_user, agent_id, normalized_session)
        with self._lock:
            service = self._services.get(key)
            if service is None:
                service = self._service_factory(definition, normalized_user)
                self._services[key] = service
            return service

    @staticmethod
    def _normalize(value: str | None, *, fallback: str) -> str:
        normalized = (value or "").strip()
        return (normalized or fallback)[:128]
