from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.services.agent_catalog_service import (
    AgentCatalogService,
    AgentNotFoundError,
)
from domain.agents.conversation_creation import ConversationAgentQuestionnaire
from domain.agents.jiho import JIHO_DEFINITION
from infrastructure.repositories.in_memory_agent_repository import (
    InMemoryConversationAgentRepository,
)


class FakeCreationService:
    def create(self, questionnaire: ConversationAgentQuestionnaire):
        profile = replace(
            JIHO_DEFINITION.profile,
            agent_id="mina",
            display_name=questionnaire.requested_name,
        )
        return replace(JIHO_DEFINITION, profile=profile)


class AgentCatalogServiceTest(unittest.TestCase):
    def test_lists_seed_and_saves_created_agent(self) -> None:
        repository = InMemoryConversationAgentRepository((JIHO_DEFINITION,))
        service = AgentCatalogService(repository, FakeCreationService())

        created = service.create_agent(
            ConversationAgentQuestionnaire(
                requested_name="Mina",
                relationship="classmate",
                personality="calm",
                speech_style="short",
                interests="drawing",
            )
        )

        self.assertEqual(created.profile.agent_id, "mina")
        self.assertEqual(
            [item.profile.agent_id for item in service.list_agents()],
            ["jiho", "mina"],
        )
        self.assertIs(service.get_agent("mina"), created)

    def test_missing_agent_raises_domain_error(self) -> None:
        service = AgentCatalogService(
            InMemoryConversationAgentRepository(),
            FakeCreationService(),
        )

        with self.assertRaises(AgentNotFoundError):
            service.get_agent("missing")


if __name__ == "__main__":
    unittest.main()
