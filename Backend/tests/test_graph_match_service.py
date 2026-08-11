from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.services.agent_catalog_service import AgentCatalogService
from application.services.graph_match_service import GraphMatchService, GraphMatchStateError
from domain.agents.jiho import JIHO_DEFINITION
from infrastructure.repositories.in_memory_agent_repository import InMemoryConversationAgentRepository
from infrastructure.repositories.in_memory_graph_match_repository import InMemoryGraphMatchRepository
from infrastructure.adapters.game_activity_memory import GameActivityMemoryWriter


class RecordingActivityMemory:
    def __init__(self) -> None:
        self.sessions = []

    def record(self, session):
        self.sessions.append(session)
        return ()


class GraphMatchServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        agent_repository = InMemoryConversationAgentRepository((JIHO_DEFINITION,))
        catalog = AgentCatalogService(agent_repository, creation_service=None)  # type: ignore[arg-type]
        self.game_repository = InMemoryGraphMatchRepository()
        self.memory = RecordingActivityMemory()
        self.service = GraphMatchService(self.game_repository, catalog, self.memory)

    def test_completes_three_rounds_and_records_activity_once(self) -> None:
        session = self.service.start(agent_id="jiho", user_id="demo-user")

        for round_index in range(3):
            target = session.current_round.target
            session = self.service.submit_attempt(
                session.id,
                user_id="demo-user",
                function=target,
                elapsed_ms=1500,
            )
            if round_index < 2:
                session = self.service.advance(session.id, user_id="demo-user")

        self.assertTrue(session.completed)
        self.assertEqual(session.user_round_wins, 3)
        self.assertEqual(len(self.memory.sessions), 1)

    def test_cannot_advance_an_unfinished_round(self) -> None:
        session = self.service.start(agent_id="jiho", user_id="demo-user")

        with self.assertRaises(GraphMatchStateError):
            self.service.advance(session.id, user_id="demo-user")

    def test_activity_writer_limits_notable_memories_to_two(self) -> None:
        session = self.service.start(agent_id="jiho", user_id="demo-user")
        for round_index in range(3):
            session = self.service.submit_attempt(
                session.id,
                user_id="demo-user",
                function=session.current_round.target,
                elapsed_ms=1000,
            )
            if round_index < 2:
                session = self.service.advance(session.id, user_id="demo-user")

        memories = GameActivityMemoryWriter._build_memories(session)

        self.assertEqual(len(memories), 2)
        self.assertIn("beat Jiho", memories[0])
        self.assertIn("exactly matched", memories[1])


if __name__ == "__main__":
    unittest.main()
