from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.agent_session_registry import AgentSessionRegistry
from application.services.agent_catalog_service import AgentNotFoundError
from domain.agents.jiho import JIHO_DEFINITION
from infrastructure.repositories.in_memory_agent_repository import (
    InMemoryConversationAgentRepository,
)


class AgentSessionRegistryTest(unittest.TestCase):
    def test_isolates_services_by_user_agent_and_session(self) -> None:
        repository = InMemoryConversationAgentRepository((JIHO_DEFINITION,))
        created: list[tuple[str, str, object]] = []

        def factory(definition, user_id):
            service = object()
            created.append((definition.profile.agent_id, user_id, service))
            return service

        registry = AgentSessionRegistry(repository, factory)

        first = registry.get("jiho", "session-a", "user-a")
        same = registry.get("jiho", "session-a", "user-a")
        other_session = registry.get("jiho", "session-b", "user-a")
        other_user = registry.get("jiho", "session-a", "user-b")

        self.assertIs(first, same)
        self.assertIsNot(first, other_session)
        self.assertIsNot(first, other_user)
        self.assertEqual(len(created), 3)

    def test_missing_agent_is_rejected(self) -> None:
        registry = AgentSessionRegistry(
            InMemoryConversationAgentRepository(),
            lambda definition, user_id: object(),
        )

        with self.assertRaises(AgentNotFoundError):
            registry.get("missing", "session", "user")


if __name__ == "__main__":
    unittest.main()
