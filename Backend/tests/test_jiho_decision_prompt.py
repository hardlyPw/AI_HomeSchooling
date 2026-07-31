from __future__ import annotations

from pathlib import Path
import sys
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = WORKSPACE_ROOT / "Agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from jiho_decision_prompt import render_jiho_decision_prompt


class JihoDecisionPromptTest(unittest.TestCase):
    def test_render_decision_prompt_includes_context_memory_and_schema(self) -> None:
        prompt = render_jiho_decision_prompt(
            user_input="i finished the worksheet",
            long_term_memories=[{"description": "User had trouble with math."}],
            time_str="8:00 PM",
            time_ctx="evening",
            affinity=72,
            conversation_history=[
                {"role": "user", "text": "math was hard"},
                {"role": "ai", "text": "send the worksheet"},
            ],
            came_back_from="away ~5 min (eating)",
        )

        self.assertIn("behavioral decision layer", prompt)
        self.assertIn("8:00 PM (evening)", prompt)
        self.assertIn("Affinity: 72/100", prompt)
        self.assertIn("away ~5 min (eating)", prompt)
        self.assertIn("User: math was hard", prompt)
        self.assertIn("Jiho: send the worksheet", prompt)
        self.assertIn("User had trouble with math.", prompt)
        self.assertIn('"affinity_delta"', prompt)


if __name__ == "__main__":
    unittest.main()
