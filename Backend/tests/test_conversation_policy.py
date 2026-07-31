from __future__ import annotations

from pathlib import Path
import sys
import unittest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from domain.agents.conversation import AvailabilityMode, ConversationBehaviorConfig
from domain.agents.conversation_policy import AffinityPolicy, ConversationTimingPolicy


def behavior_config() -> ConversationBehaviorConfig:
    return ConversationBehaviorConfig(
        delay_turn_threshold=3,
        early_away_probability=0.1,
        late_away_probability=0.5,
        always_cooldown_probability=0.01,
        cooldown_seconds=300,
        cooldown_reasons=("busy",),
    )


class ConversationTimingPolicyTest(unittest.TestCase):
    def test_picks_normal_when_no_away_probability_hits(self) -> None:
        policy = ConversationTimingPolicy(behavior_config())

        result = policy.pick_away_decision(
            turn_count=0,
            away_count=0,
            random_value=lambda: 0.9,
        )

        self.assertEqual(result.decision.mode, AvailabilityMode.NORMAL)
        self.assertEqual(result.away_count, 0)

    def test_force_cooldown_consumes_debug_flag(self) -> None:
        policy = ConversationTimingPolicy(behavior_config())

        result = policy.pick_away_decision(
            turn_count=0,
            away_count=0,
            force_cooldown=True,
            choose_reason=lambda reasons: reasons[0],
        )

        self.assertEqual(result.decision.mode, AvailabilityMode.COOLDOWN)
        self.assertEqual(result.decision.wait_seconds, 300)
        self.assertEqual(result.decision.reason, "busy")
        self.assertEqual(result.away_count, 1)
        self.assertTrue(result.consumed_forced_cooldown)

    def test_repeated_away_event_escalates_to_cooldown(self) -> None:
        policy = ConversationTimingPolicy(behavior_config())

        result = policy.pick_away_decision(
            turn_count=10,
            away_count=4,
            random_value=lambda: 0.02,
            choose_reason=lambda reasons: reasons[0],
        )

        self.assertEqual(result.decision.mode, AvailabilityMode.COOLDOWN)
        self.assertEqual(result.away_count, 6)


class AffinityPolicyTest(unittest.TestCase):
    def test_negative_streak_amplifies_negative_delta(self) -> None:
        policy = AffinityPolicy(behavior_config())

        result = policy.apply_delta(
            current_affinity=70,
            delta=-2,
            consecutive_negative=2,
        )

        self.assertEqual(result.next_affinity, 66)
        self.assertEqual(result.actual_delta, -4)
        self.assertEqual(result.consecutive_negative, 3)

    def test_positive_delta_resets_negative_streak_and_clamps_affinity(self) -> None:
        policy = AffinityPolicy(behavior_config())

        result = policy.apply_delta(
            current_affinity=99,
            delta=5,
            consecutive_negative=4,
        )

        self.assertEqual(result.next_affinity, 100)
        self.assertEqual(result.actual_delta, 1)
        self.assertEqual(result.consecutive_negative, 0)


if __name__ == "__main__":
    unittest.main()
