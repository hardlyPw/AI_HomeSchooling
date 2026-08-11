from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.services.agent_creation_service import ConversationAgentCreationService
from domain.agents.conversation import ConversationPersonaConfig, GameSkillTier
from domain.agents.conversation_creation import (
    ConversationAgentQuestionnaire,
    GeneratedConversationAgentDesign,
)
from domain.agents.conversation_presets import (
    AffinitySensitivityLevel,
    AvailabilityLevel,
    ConversationBehaviorSelection,
    CooldownLevel,
    DoubleTextLevel,
    InitialClosenessLevel,
    ReplyDelayLevel,
)
from domain.agents.definition import AgentType


class FakeAgentDesigner:
    def design(self, questionnaire: ConversationAgentQuestionnaire):
        self.questionnaire = questionnaire
        return GeneratedConversationAgentDesign(
            display_name="Mina",
            description="A thoughtful friend who likes drawing.",
            persona=ConversationPersonaConfig(
                narrative=(
                    "[About You]\nMina draws after school.\n"
                    "[Personality]\nThoughtful."
                ),
                user_profile="A same-age school friend.",
                decision_guidance="Replies carefully and changes topics gently.",
                affinity_rubric="Honesty raises affinity; cruelty lowers it.",
                affinity_stage_directions=(
                    "Use a minimal reply.",
                    "Stay reserved.",
                    "Talk naturally.",
                    "Share personal thoughts.",
                ),
                behavior_bans=("Do not overpraise.", "Do not lecture."),
            ),
            behavior_selection=ConversationBehaviorSelection(
                availability=AvailabilityLevel.BALANCED,
                reply_delay=ReplyDelayLevel.SHORT,
                cooldown=CooldownLevel.OCCASIONAL,
                double_text=DoubleTextLevel.FREQUENT,
                affinity_sensitivity=AffinitySensitivityLevel.REACTIVE,
                initial_closeness=InitialClosenessLevel.ACQUAINTED,
            ),
            cooldown_reasons=("drawing", "at art club"),
            game_skill_tier=GameSkillTier.HARD,
        )


class AgentCreationServiceTest(unittest.TestCase):
    def test_builds_definition_from_llm_text_and_system_presets(self) -> None:
        designer = FakeAgentDesigner()
        service = ConversationAgentCreationService(
            designer,
            id_factory=lambda _: "mina-test",
        )
        questionnaire = ConversationAgentQuestionnaire(
            requested_name="Mina",
            relationship="same-class friend",
            personality="thoughtful and quiet",
            speech_style="short casual messages",
            interests="drawing",
        )

        definition = service.create(questionnaire)

        self.assertEqual(definition.agent_type, AgentType.CONVERSATION)
        self.assertEqual(definition.profile.agent_id, "mina-test")
        self.assertEqual(definition.profile.initial_affinity, 50)
        self.assertEqual(definition.profile.game_skill_tier, GameSkillTier.HARD)
        self.assertEqual(
            definition.profile.persona.behavior_bans[0],
            "Do not overpraise.",
        )
        self.assertEqual(definition.behavior.initial_delayed_reply_seconds, 10)
        self.assertEqual(definition.behavior.double_text_probability, 0.25)
        self.assertEqual(definition.behavior.affinity_negative_step, -2)
        self.assertEqual(
            definition.behavior.cooldown_reasons,
            ("drawing", "at art club"),
        )
        self.assertTrue(definition.runtime.system_safety_rules)
        self.assertEqual(definition.runtime.response_model.model, "gpt-4o")
        self.assertIs(designer.questionnaire, questionnaire)


if __name__ == "__main__":
    unittest.main()
