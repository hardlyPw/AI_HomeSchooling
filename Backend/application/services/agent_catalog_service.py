from __future__ import annotations

from domain.agents.conversation import ConversationAgentDefinition
from domain.agents.conversation_creation import ConversationAgentQuestionnaire
from domain.agents.repository import ConversationAgentRepository
from application.services.agent_creation_service import ConversationAgentCreationService


class AgentNotFoundError(LookupError):
    pass


class AgentCatalogService:
    def __init__(
        self,
        repository: ConversationAgentRepository,
        creation_service: ConversationAgentCreationService,
    ) -> None:
        self._repository = repository
        self._creation_service = creation_service

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
