from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from domain.agents.definition import AgentType
from domain.agents.conversation_presets import ConversationPresetResolver
from domain.agents.jiho import (
    JIHO_BEHAVIOR,
    JIHO_BEHAVIOR_SELECTION,
    JIHO_COOLDOWN_REASONS,
    JIHO_DEFINITION,
    JIHO_PROFILE,
)


class AgentDefinitionTest(unittest.TestCase):
    def test_jiho_definition_aggregates_static_agent_configuration(self) -> None:
        self.assertEqual(JIHO_DEFINITION.agent_type, AgentType.CONVERSATION)
        self.assertIs(JIHO_DEFINITION.profile, JIHO_PROFILE)
        self.assertIs(JIHO_DEFINITION.behavior, JIHO_BEHAVIOR)
        self.assertEqual(JIHO_DEFINITION.profile.agent_id, "jiho")

    def test_jiho_behavior_is_fully_reproducible_from_presets(self) -> None:
        resolver = ConversationPresetResolver()

        behavior = resolver.resolve_behavior(
            JIHO_BEHAVIOR_SELECTION,
            cooldown_reasons=JIHO_COOLDOWN_REASONS,
        )

        self.assertEqual(behavior, JIHO_BEHAVIOR)
        self.assertEqual(
            resolver.resolve_initial_affinity(JIHO_BEHAVIOR_SELECTION),
            JIHO_PROFILE.initial_affinity,
        )

    def test_jiho_definition_tracks_all_fixed_runtime_settings(self) -> None:
        runtime = JIHO_DEFINITION.runtime

        self.assertEqual(
            (
                runtime.response_model.model,
                runtime.response_model.temperature,
                runtime.response_model.max_tokens,
            ),
            ("gpt-4o", 0.8, 300),
        )
        self.assertEqual(
            (
                runtime.decision_model.model,
                runtime.decision_model.temperature,
                runtime.decision_model.max_tokens,
            ),
            ("gpt-4o-mini", 0.6, 200),
        )
        self.assertEqual(runtime.prompt.response_history_limit, 20)
        self.assertEqual(runtime.prompt.decision_history_limit, 8)
        self.assertEqual(runtime.prompt.affinity_stage_maxima, (30, 49, 69))
        self.assertEqual(
            (runtime.prompt.affinity_delta_min, runtime.prompt.affinity_delta_max),
            (-10, 10),
        )
        self.assertEqual(
            (
                runtime.memory.low_affinity_top_k,
                runtime.memory.normal_top_k,
                runtime.memory.top_k_affinity_cutoff,
            ),
            (1, 5, 40),
        )
        self.assertEqual(runtime.memory.session_timeout_seconds, 300)
        self.assertEqual(runtime.memory.table_name, "friend_memories_v2")
        self.assertEqual(runtime.memory.match_rpc_name, "match_friend_memories_v2")
        self.assertEqual(
            runtime.memory.reset_rpc_name,
            "reset_friend_memories_v2_to_demo_seed",
        )
        self.assertTrue(runtime.system_safety_rules)
        self.assertTrue(JIHO_PROFILE.persona.behavior_bans)


if __name__ == "__main__":
    unittest.main()
