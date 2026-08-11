from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.services.agent_catalog_service import AgentCatalogService
from application.services.graph_match_service import GraphMatchService
from domain.agents.jiho import JIHO_DEFINITION
from domain.games.graph_match import QuickChat
from infrastructure.repositories.in_memory_agent_repository import InMemoryConversationAgentRepository
from infrastructure.repositories.supabase_graph_match_repository import SupabaseGraphMatchRepository
from infrastructure.repositories.resilient_graph_match_repository import ResilientGraphMatchRepository


class FakeQuery:
    def __init__(self, client, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.action = ""
        self.payload = None
        self.conflicts: list[str] = []
        self.filters: list[tuple[str, object]] = []
        self.order_column = ""
        self.limit_count: int | None = None

    def upsert(self, payload, *, on_conflict: str):
        self.action = "upsert"
        self.payload = payload if isinstance(payload, list) else [payload]
        self.conflicts = on_conflict.split(",")
        return self

    def select(self, columns: str):
        self.action = "select"
        return self

    def eq(self, column: str, value):
        self.filters.append((column, value))
        return self

    def order(self, column: str):
        self.order_column = column
        return self

    def limit(self, count: int):
        self.limit_count = count
        return self

    def execute(self):
        rows = self.client.rows.setdefault(self.table_name, [])
        if self.action == "upsert":
            for payload in self.payload:
                existing = next(
                    (
                        row
                        for row in rows
                        if all(row.get(key) == payload.get(key) for key in self.conflicts)
                    ),
                    None,
                )
                if existing is None:
                    rows.append(dict(payload))
                else:
                    existing.update(payload)
            return SimpleNamespace(data=self.payload)

        selected = [
            dict(row)
            for row in rows
            if all(row.get(column) == value for column, value in self.filters)
        ]
        if self.order_column:
            selected.sort(key=lambda row: row[self.order_column])
        if self.limit_count is not None:
            selected = selected[: self.limit_count]
        return SimpleNamespace(data=selected)


class FakeSupabase:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict]] = {}

    def table(self, table_name: str) -> FakeQuery:
        return FakeQuery(self, table_name)


class NoopMemory:
    def record(self, session):
        return ("The user completed Graph Match.",)


class SupabaseGraphMatchRepositoryTest(unittest.TestCase):
    def test_persists_and_restores_complete_game(self) -> None:
        client = FakeSupabase()
        repository = SupabaseGraphMatchRepository(client)
        catalog = AgentCatalogService(
            InMemoryConversationAgentRepository((JIHO_DEFINITION,)),
            creation_service=None,  # type: ignore[arg-type]
        )
        service = GraphMatchService(repository, catalog, NoopMemory())
        session = service.start(agent_id="jiho", user_id="demo-user")
        service.send_quick_chat(session.id, user_id="demo-user", chat=QuickChat.HELLO)

        for index in range(3):
            session = service.submit_attempt(
                session.id,
                user_id="demo-user",
                function=session.current_round.target,
                elapsed_ms=10_000 + index * 1000,
            )
            if index < 2:
                session = service.advance(session.id, user_id="demo-user")

        restored = SupabaseGraphMatchRepository(client).get(session.id)

        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertTrue(restored.completed)
        self.assertEqual(len(restored.rounds), 3)
        self.assertEqual(restored.rounds[0].best_attempt.score, 108.3)
        self.assertEqual(restored.quick_chats[0].chat, QuickChat.HELLO)
        self.assertEqual(restored.activity_memories, ("The user completed Graph Match.",))

    def test_resilient_repository_keeps_session_when_remote_is_offline(self) -> None:
        class OfflineRepository:
            def save(self, session):
                raise ConnectionError("offline")

            def get(self, session_id):
                raise ConnectionError("offline")

        repository = ResilientGraphMatchRepository(OfflineRepository())
        catalog = AgentCatalogService(
            InMemoryConversationAgentRepository((JIHO_DEFINITION,)),
            creation_service=None,  # type: ignore[arg-type]
        )
        service = GraphMatchService(repository, catalog, NoopMemory())

        session = service.start(agent_id="jiho", user_id="demo-user")

        self.assertIs(repository.get(session.id), session)


if __name__ == "__main__":
    unittest.main()
