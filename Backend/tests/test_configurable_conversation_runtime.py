from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from domain.agents.jiho import JIHO_DEFINITION
from infrastructure.adapters.configurable_conversation_runtime import (
    ConfigurableConversationRuntime,
)
from infrastructure.storage.namespaced_conversation_memory import (
    NamespacedConversationMemoryStore,
)


class ConfigurableConversationRuntimeTest(unittest.TestCase):
    def make_runtime(self, user_id: str, agent_id: str, store):
        profile = replace(JIHO_DEFINITION.profile, agent_id=agent_id)
        definition = replace(JIHO_DEFINITION, profile=profile)
        return ConfigurableConversationRuntime(
            definition=definition,
            user_id=user_id,
            openai_client=SimpleNamespace(),
            memory_store=store,
        )

    def test_long_term_memory_is_namespaced_by_user_and_agent(self) -> None:
        store = NamespacedConversationMemoryStore()
        first = self.make_runtime("user-a", "jiho", store)
        other_user = self.make_runtime("user-b", "jiho", store)
        other_agent = self.make_runtime("user-a", "mina", store)

        first.record_turn("math homework was hard", "send me the problem", False)

        self.assertEqual(len(first.get_long_term_memory("math", 5)), 1)
        self.assertEqual(other_user.get_long_term_memory("math", 5), [])
        self.assertEqual(other_agent.get_long_term_memory("math", 5), [])

    def test_prompt_uses_definition_persona_bans_and_fixed_safety(self) -> None:
        runtime = self.make_runtime(
            "user-a",
            "jiho",
            NamespacedConversationMemoryStore(),
        )

        prompt = runtime.build_prompt(
            user_input="hello",
            long_term_memories=[],
            long_term_k=1,
            decision={"timing": "instant", "action": "normal"},
            agent_emotion_info={"emotion": "neutral", "reason": ""},
            time_str="10:00 AM",
            time_ctx="morning",
        )

        self.assertIn(JIHO_DEFINITION.profile.persona.narrative, prompt)
        self.assertIn(JIHO_DEFINITION.profile.persona.behavior_bans[0], prompt)
        self.assertIn(JIHO_DEFINITION.runtime.system_safety_rules[0], prompt)


if __name__ == "__main__":
    unittest.main()
