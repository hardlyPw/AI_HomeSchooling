from __future__ import annotations

from pathlib import Path
import sys
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from api.v1.agents import router
from application.dependencies import get_agent_catalog_service
from application.services.agent_catalog_service import AgentCatalogService
from application.services.agent_creation_service import ConversationAgentCreationService
from domain.agents.conversation import ConversationPersonaConfig, GameSkillTier
from domain.agents.conversation_creation import GeneratedConversationAgentDesign
from domain.agents.conversation_presets import (
    AffinitySensitivityLevel,
    AvailabilityLevel,
    ConversationBehaviorSelection,
    CooldownLevel,
    DoubleTextLevel,
    InitialClosenessLevel,
    ReplyDelayLevel,
)
from infrastructure.repositories.in_memory_agent_repository import (
    InMemoryConversationAgentRepository,
)


class FakeDesigner:
    def design(self, questionnaire):
        return GeneratedConversationAgentDesign(
            display_name=questionnaire.requested_name,
            description="A calm friend who likes drawing.",
            persona=ConversationPersonaConfig(
                narrative="Mina is calm, honest, and playful.",
                user_profile="The user is Mina's classmate.",
                decision_guidance="Reply briefly and react to the latest message.",
                affinity_rubric="Trust grows through honest conversation.",
                affinity_stage_directions=("distant", "polite", "friendly", "close"),
                behavior_bans=("Do not lecture.",),
            ),
            behavior_selection=ConversationBehaviorSelection(
                availability=AvailabilityLevel.BALANCED,
                reply_delay=ReplyDelayLevel.STANDARD,
                cooldown=CooldownLevel.RARE,
                double_text=DoubleTextLevel.OCCASIONAL,
                affinity_sensitivity=AffinitySensitivityLevel.BALANCED,
                initial_closeness=InitialClosenessLevel.FRIEND,
            ),
            cooldown_reasons=("busy drawing",),
            game_skill_tier=GameSkillTier.EASY,
        )


class AgentsApiTest(unittest.TestCase):
    def setUp(self) -> None:
        repository = InMemoryConversationAgentRepository()
        creation_service = ConversationAgentCreationService(
            FakeDesigner(),
            id_factory=lambda name: "mina",
        )
        catalog = AgentCatalogService(repository, creation_service)
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/agents")
        app.dependency_overrides[get_agent_catalog_service] = lambda: catalog
        self.client = TestClient(app)

    def test_create_then_list_agent(self) -> None:
        response = self.client.post("/api/v1/agents", json={
            "requested_name": "Mina",
            "relationship": "classmate",
            "personality": "calm and playful",
            "speech_style": "short messages",
            "interests": "drawing",
        })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["id"], "mina")
        self.assertEqual(response.json()["game_skill_tier"], "easy")
        self.assertTrue(response.json()["is_online"])
        listed = self.client.get("/api/v1/agents")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(listed.json()["agents"][0]["name"], "Mina")
        self.assertTrue(listed.json()["agents"][0]["is_online"])

    def test_invalid_request_is_rejected_before_designer(self) -> None:
        response = self.client.post("/api/v1/agents", json={
            "requested_name": "",
            "relationship": "classmate",
            "personality": "calm",
            "speech_style": "short",
            "interests": "drawing",
        })

        self.assertEqual(response.status_code, 422)

    def test_created_agent_can_be_deleted(self) -> None:
        self.client.post("/api/v1/agents", json={
            "requested_name": "Mina",
            "relationship": "classmate",
            "personality": "calm",
            "speech_style": "short",
            "interests": "drawing",
        })

        response = self.client.delete("/api/v1/agents/mina")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(self.client.get("/api/v1/agents").json()["agents"], [])


if __name__ == "__main__":
    unittest.main()
