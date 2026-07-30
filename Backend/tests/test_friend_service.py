from __future__ import annotations

from pathlib import Path
from dataclasses import replace
import sys
import unittest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.friend_service import FriendService
from domain.agents.conversation import ConversationBehaviorConfig
from domain.agents.conversation_policy import ConversationTimingPolicy
from domain.agents.jiho import JIHO_BEHAVIOR, JIHO_PROFILE


class FakeFriendRuntime:
    def __init__(self) -> None:
        self.affinity = 70
        self.consecutive_negative = 0
        self.conversation_history: list[dict] = []
        self.uses_long_term_memory = False
        self.last_response_usage = {"prompt_tokens": 3, "completion_tokens": 4}
        self.reset_values: list[int] = []
        self.demo_memory_reset = False
        self.recorded_turn: tuple[str, str, bool] | None = None
        self.prompt_payload: dict | None = None

    def reset_state(self, initial_affinity: int) -> None:
        self.reset_values.append(initial_affinity)
        self.affinity = initial_affinity
        self.conversation_history.clear()
        self.consecutive_negative = 0

    def reset_demo_long_term_memory(self) -> None:
        self.demo_memory_reset = True

    def get_long_term_memory(self, query_text: str, top_k: int) -> list[dict]:
        return [{"description": f"{query_text}:{top_k}", "score": 1}]

    def consume_time_context_for_turn(self) -> tuple[str, str | None]:
        return "10:00 AM", "school hours"

    def make_decision(
        self,
        user_message: str,
        long_term_memory: list[dict],
        time_str: str,
        time_context: str | None,
    ) -> dict:
        return {
            "emotion": "amused",
            "emotion_reason": "the user sounds casual",
            "timing": "instant",
            "action": "normal",
            "session_break": True,
            "affinity_delta": 2,
            "affinity_reason": "normal chat",
            "reasoning": "simple reply",
        }

    def build_prompt(
        self,
        *,
        user_input: str,
        long_term_memories: list[dict],
        long_term_k: int,
        decision: dict,
        agent_emotion_info: dict,
        time_str: str,
        time_ctx: str | None,
    ) -> str:
        self.prompt_payload = {
            "user_input": user_input,
            "long_term_memories": long_term_memories,
            "long_term_k": long_term_k,
            "decision": decision,
            "agent_emotion_info": agent_emotion_info,
            "time_str": time_str,
            "time_ctx": time_ctx,
        }
        return "prompt"

    def generate_response(self, prompt: str) -> str:
        return "first|second"

    def split_double_text(self, response: str) -> list[str]:
        return response.split("|")

    def stream_response(self, prompt: str):  # pragma: no cover - unused by double-text test
        return iter(())

    def append_turn_to_short_term_memory(self, user_message: str, reply: str) -> None:
        self.conversation_history.append({"role": "user", "text": user_message})
        self.conversation_history.append({"role": "ai", "text": reply})

    def record_turn(self, user_message: str, reply: str, session_break: bool) -> None:
        self.recorded_turn = (user_message, reply, session_break)


class FriendServiceTest(unittest.TestCase):
    def service_with_fake_runtime(self) -> tuple[FriendService, FakeFriendRuntime]:
        runtime = FakeFriendRuntime()
        service = FriendService(
            runtime=runtime,
            profile=JIHO_PROFILE,
            behavior=JIHO_BEHAVIOR,
        )
        service._timing_policy = ConversationTimingPolicy(
            ConversationBehaviorConfig(
                delay_turn_threshold=100,
                early_away_probability=0,
                late_away_probability=0,
                always_cooldown_probability=0,
                cooldown_seconds=0,
                cooldown_reasons=("test",),
            )
        )
        return service, runtime

    def test_service_uses_injected_profile_instead_of_jiho_defaults(self) -> None:
        runtime = FakeFriendRuntime()
        profile = replace(
            JIHO_PROFILE,
            agent_id="another-friend",
            display_name="Another Friend",
            initial_affinity=25,
            affinity_min=20,
            affinity_max=30,
        )
        service = FriendService(
            runtime=runtime,
            profile=profile,
            behavior=JIHO_BEHAVIOR,
        )

        runtime.affinity = 29
        service._apply_delta(10)

        self.assertEqual(runtime.reset_values, [25])
        self.assertEqual(runtime.affinity, 30)

    def test_reset_uses_runtime_and_resets_demo_memory(self) -> None:
        service, runtime = self.service_with_fake_runtime()

        runtime.affinity = 10
        runtime.conversation_history.append({"role": "user", "text": "old"})
        service.force_next_cooldown()
        service.force_next_double_text()

        service.reset()

        self.assertEqual(runtime.affinity, 70)
        self.assertEqual(runtime.conversation_history, [])
        self.assertTrue(runtime.demo_memory_reset)
        self.assertEqual(runtime.reset_values, [70, 70])

    def test_stream_reply_can_run_with_fake_runtime(self) -> None:
        service, runtime = self.service_with_fake_runtime()
        service.force_next_double_text()

        events = [event.to_payload() for event in service.stream_reply("yo")]

        decision_event = next(event for event in events if "decision" in event)
        self.assertEqual(decision_event["decision"]["affinity_prev"], 70)
        self.assertEqual(decision_event["decision"]["affinity_next"], 72)
        self.assertEqual(decision_event["decision"]["affinity_delta"], 2)
        self.assertIn({"delta": "first"}, events)
        self.assertIn({"message_break": True}, events)
        self.assertIn({"delta": "second"}, events)
        self.assertIn({"tokens": {
            "decision_prompt": None,
            "decision_completion": None,
            "reply_prompt": 3,
            "reply_completion": 4,
            "total": 7,
        }}, events)
        self.assertEqual(events[-1], {"done": True})
        self.assertEqual(runtime.conversation_history[-2:], [
            {"role": "user", "text": "yo"},
            {"role": "ai", "text": "first second"},
        ])
        self.assertEqual(runtime.recorded_turn, ("yo", "first second", True))
        self.assertEqual(runtime.prompt_payload["user_input"], "yo")


if __name__ == "__main__":
    unittest.main()
