from __future__ import annotations

from pathlib import Path
import sys
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = WORKSPACE_ROOT / "Agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from jiho_prompt import render_jiho_prompt
from jiho_prompt import AI_PERSONA
from domain.agents.jiho import JIHO_PROFILE


class JihoPromptTest(unittest.TestCase):
    def test_domain_profile_uses_prompt_persona_source(self) -> None:
        self.assertEqual(JIHO_PROFILE.persona.narrative, AI_PERSONA)

    def test_render_prompt_includes_persona_context_and_behavioral_cues(self) -> None:
        prompt = render_jiho_prompt(
            user_input="yo i finished the homework",
            affinity=75,
            long_term_memories=[{"description": "User struggled with math homework."}],
            long_term_k=1,
            conversation_history=[
                {"role": "user", "text": "math was hard"},
                {"role": "ai", "text": "send the problem"},
            ],
            agent_emotion_info={"emotion": "amused", "reason": "user actually did it"},
            decision={"timing": "double_text", "action": "normal"},
            time_str="10:00 PM",
            time_ctx="late for a 7th grader",
        )

        self.assertIn("You are Jiho.", prompt)
        self.assertIn("User struggled with math homework.", prompt)
        self.assertIn("User: math was hard", prompt)
        self.assertIn("Jiho: send the problem", prompt)
        self.assertIn("[Your Current Emotion]", prompt)
        self.assertIn("[Behavioral Cues", prompt)
        self.assertIn("double-text", prompt.lower())
        self.assertIn("[Current Time]", prompt)


if __name__ == "__main__":
    unittest.main()
