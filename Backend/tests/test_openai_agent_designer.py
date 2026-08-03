from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from domain.agents.conversation_creation import ConversationAgentQuestionnaire
from domain.agents.conversation_presets import (
    AffinitySensitivityLevel,
    AvailabilityLevel,
)
from infrastructure.adapters.openai_agent_designer import (
    AGENT_DESIGNER_MAX_TOKENS,
    AGENT_DESIGNER_MODEL,
    OpenAIConversationAgentDesigner,
)


class FakeCompletions:
    def create(self, **kwargs):
        self.kwargs = kwargs
        payload = {
            "display_name": "Mina",
            "description": "A calm art-club friend.",
            "persona": {
                "narrative": "[About You]\nMina draws.\n[Personality]\nCalm.",
                "user_profile": "A same-age friend.",
                "decision_guidance": "Reply thoughtfully.",
                "affinity_rubric": "Honesty raises affinity.",
                "affinity_stage_directions": [
                    "minimal",
                    "reserved",
                    "natural",
                    "open",
                ],
                "behavior_bans": [
                    "no lectures",
                    "no overpraise",
                    "no formal tone",
                    "no fake enthusiasm",
                    "no repeated questions",
                ],
            },
            "behavior_selection": {
                "availability": "balanced",
                "reply_delay": "standard",
                "cooldown": "rare",
                "double_text": "occasional",
                "affinity_sensitivity": "reactive",
                "initial_closeness": "friend",
            },
            "cooldown_reasons": ["drawing", "at art club", "eating"],
        }
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))]
        )


class OpenAIAgentDesignerTest(unittest.TestCase):
    def test_requests_json_and_parses_only_constrained_behavior_values(self) -> None:
        completions = FakeCompletions()
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        designer = OpenAIConversationAgentDesigner(client)

        design = designer.design(
            ConversationAgentQuestionnaire(
                requested_name="Mina",
                relationship="classmate",
                personality="calm",
                speech_style="short casual messages",
                interests="drawing",
            )
        )

        self.assertEqual(design.behavior_selection.availability, AvailabilityLevel.BALANCED)
        self.assertEqual(
            design.behavior_selection.affinity_sensitivity,
            AffinitySensitivityLevel.REACTIVE,
        )
        self.assertEqual(completions.kwargs["model"], AGENT_DESIGNER_MODEL)
        self.assertEqual(completions.kwargs["max_tokens"], AGENT_DESIGNER_MAX_TOKENS)
        self.assertEqual(completions.kwargs["response_format"], {"type": "json_object"})
        system_prompt = completions.kwargs["messages"][0]["content"]
        self.assertIn("Do not output probabilities", system_prompt)
        self.assertIn("System safety is fixed elsewhere", system_prompt)


if __name__ == "__main__":
    unittest.main()
