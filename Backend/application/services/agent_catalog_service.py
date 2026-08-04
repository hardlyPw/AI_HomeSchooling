from __future__ import annotations

from domain.agents.conversation import ConversationAgentDefinition
from domain.agents.conversation_creation import ConversationAgentQuestionnaire
from domain.agents.repository import ConversationAgentRepository
from application.services.agent_creation_service import ConversationAgentCreationService


class AgentNotFoundError(LookupError):
    pass


class ProtectedAgentError(ValueError):
    pass


class AgentCatalogService:
    def __init__(
        self,
        repository: ConversationAgentRepository,
        creation_service: ConversationAgentCreationService,
        *,
        protected_agent_ids: frozenset[str] = frozenset({"jiho"}),
    ) -> None:
        self._repository = repository
        self._creation_service = creation_service
        self._protected_agent_ids = protected_agent_ids

    def list_agents(self) -> list[ConversationAgentDefinition]:
        return self._repository.list_all()

    def get_agent(self, agent_id: str) -> ConversationAgentDefinition:
        definition = self._repository.get(agent_id)
        if definition is None:
            raise AgentNotFoundError(agent_id)
        return definition

    def create_agent(
        self,
        questionnaire: ConversationAgentQuestionnaire,
    ) -> ConversationAgentDefinition:
        definition = self._creation_service.create(questionnaire)
        self._repository.save(definition)
        return definition

    def is_protected(self, agent_id: str) -> bool:
        return agent_id in self._protected_agent_ids

    def delete_agent(self, agent_id: str) -> None:
        if self.is_protected(agent_id):
            raise ProtectedAgentError(agent_id)
        if not self._repository.delete(agent_id):
            raise AgentNotFoundError(agent_id)
