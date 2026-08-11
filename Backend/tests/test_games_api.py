from __future__ import annotations

from pathlib import Path
import sys
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.v1.games import router
from application.dependencies import get_graph_match_service
from application.services.agent_catalog_service import AgentCatalogService
from application.services.graph_match_service import GraphMatchService
from domain.agents.jiho import JIHO_DEFINITION
from infrastructure.repositories.in_memory_agent_repository import InMemoryConversationAgentRepository
from infrastructure.repositories.in_memory_graph_match_repository import InMemoryGraphMatchRepository


class NoopMemory:
    def record(self, session):
        return ()


class GamesApiTest(unittest.TestCase):
    def setUp(self) -> None:
        catalog = AgentCatalogService(
            InMemoryConversationAgentRepository((JIHO_DEFINITION,)),
            creation_service=None,  # type: ignore[arg-type]
        )
        service = GraphMatchService(InMemoryGraphMatchRepository(), catalog, NoopMemory())
        self.service = service
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/games")
        app.dependency_overrides[get_graph_match_service] = lambda: service
        self.client = TestClient(app)

    def test_starts_game_and_reveals_formula_after_exact_attempt(self) -> None:
        started = self.client.post(
            "/api/v1/games/graph-match/sessions",
            json={"agent_id": "jiho"},
        )
        self.assertEqual(started.status_code, 201)
        payload = started.json()
        self.assertEqual(payload["agent_skill"], "normal")
        self.assertIsNone(payload["current_round"]["target_latex"])

        session_id = payload["id"]
        target = self.service.get(session_id, user_id="demo-user").current_round.target
        attempted = self.client.post(
            f"/api/v1/games/graph-match/sessions/{session_id}/attempts",
            json={
                "coefficient": target.coefficient,
                "base": target.base,
                "horizontal_shift": target.horizontal_shift,
                "vertical_shift": target.vertical_shift,
                "elapsed_ms": 1200,
            },
        )

        self.assertEqual(attempted.status_code, 200)
        self.assertTrue(attempted.json()["current_round"]["completed"])
        self.assertIsNotNone(attempted.json()["current_round"]["target_latex"])
        self.assertEqual(attempted.json()["current_round"]["attempts"][0]["graph_score"], 100.0)
        self.assertEqual(attempted.json()["current_round"]["attempts"][0]["time_bonus"], 9.8)
        self.assertEqual(len(attempted.json()["rounds"]), 3)


if __name__ == "__main__":
    unittest.main()
