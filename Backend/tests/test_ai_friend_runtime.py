from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from infrastructure.adapters.ai_friend_runtime import AIFriendRuntime
from infrastructure.adapters.ai_friend_state import AIFriendStateAdapter


class FakeSupabase:
    def __init__(self) -> None:
        self.called_rpc = ""

    def rpc(self, name: str, payload: dict) -> "FakeSupabase":
        self.called_rpc = name
        self.payload = payload
        return self

    def execute(self) -> None:
        return None


class FakeTimeTracker:
    def get_time_context(self) -> tuple[str, str]:
        return "10:00 PM", "late for a 7th grader"

    def consume_for_turn(self) -> tuple[str, str]:
        return "10:00 PM", "late for a 7th grader"


class FakeCompletions:
    def __init__(self, contents: list[str]) -> None:
        self.contents = contents

    def create(self, **kwargs):
        content = self.contents.pop(0)
        message = SimpleNamespace(content=content)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=11, completion_tokens=7)
        return SimpleNamespace(choices=[choice], usage=usage)


class FakeOpenAIClient:
    def __init__(self, contents: list[str]) -> None:
        self.chat = SimpleNamespace(completions=FakeCompletions(contents))


class FakeMemoryRepository:
    def __init__(self) -> None:
        self.recorded_turn = None
        self.drain_count = 0

    def get_long_term_memory(self, query_text: str, top_k: int) -> list[dict]:
        return [{"description": f"repository memory for {query_text}", "top_k": top_k}]

    def record_turn(self, user: str, reply: str, session_break: bool = False) -> None:
        self.recorded_turn = (user, reply, session_break)

    def drain_pending_chunk(self) -> list[dict]:
        self.drain_count += 1
        return []


def fake_module() -> SimpleNamespace:
    module = SimpleNamespace()
    module.affinity = 70
    module.consecutive_negative = 0
    module.conversation_history = []
    module.USE_LONG_TERM_MEMORY = True
    module.last_response_usage = {"prompt_tokens": 1, "completion_tokens": 2}
    module.supabase = FakeSupabase()
    module._cooldown_until = "set"
    module._cooldown_reason = "busy"
    module._drain_pending_chunk = lambda: None
    module.get_long_term_memory = lambda query_text, top_k: [
        {"query": query_text, "top_k": top_k}
    ]
    module._consume_time_context_for_turn = lambda: ("10:00", "morning")
    module.make_decision = lambda user, memory, time_str, time_ctx: {
        "user": user,
        "memory": memory,
        "time_str": time_str,
        "time_ctx": time_ctx,
    }
    module.build_prompt = lambda **kwargs: f"prompt:{kwargs['user_input']}"
    module.generate_ai_response = lambda prompt: f"reply:{prompt}"
    module._split_double_text = lambda response: response.split("|")
    module.record_turn = lambda user, reply, session_break=False: setattr(
        module,
        "recorded_turn",
        (user, reply, session_break),
    )
    module.openai_client = SimpleNamespace()
    return module


def fake_native_module() -> SimpleNamespace:
    module = fake_module()
    module._memory_repository = FakeMemoryRepository()
    module.runtime_state = SimpleNamespace(
        affinity=73,
        consecutive_negative=0,
        conversation_history=[{"role": "user", "text": "math was hard"}],
        cooldown_until=None,
        cooldown_reason="",
        last_response_time=SimpleNamespace(),
        last_response_usage=None,
        time_context_tracker=FakeTimeTracker(),
        reset=lambda initial_affinity: None,
    )
    module.DEBUG_PROMPT = False
    module.openai_client = FakeOpenAIClient(
        [
            '{"timing": "double_text", "action": "normal", "session_break": false, "affinity_delta": 2, "affinity_reason": "steady"}',
            "first. second.",
        ]
    )
    module.get_long_term_memory = lambda query_text, top_k: [
        {"description": f"memory for {query_text}", "score": 1.0}
    ]
    return module


class AIFriendRuntimeTest(unittest.TestCase):
    def test_runtime_delegates_state_memory_decision_prompt_and_response(self) -> None:
        module = fake_module()
        runtime = AIFriendRuntime(module)

        runtime.reset_state(initial_affinity=55)
        self.assertEqual(runtime.affinity, 55)
        self.assertEqual(runtime.consecutive_negative, 0)
        self.assertEqual(runtime.conversation_history, [])

        runtime.affinity = 40
        runtime.consecutive_negative = 2
        self.assertEqual(runtime.affinity, 40)
        self.assertEqual(runtime.consecutive_negative, 2)

        self.assertTrue(runtime.uses_long_term_memory)
        self.assertEqual(
            runtime.get_long_term_memory("hello", 3),
            [{"query": "hello", "top_k": 3}],
        )

        time_str, time_ctx = runtime.consume_time_context_for_turn()
        decision = runtime.make_decision("hi", [], time_str, time_ctx)
        self.assertEqual(decision["time_str"], "10:00")
        self.assertEqual(decision["time_ctx"], "morning")

        prompt = runtime.build_prompt(
            user_input="hi",
            long_term_memories=[],
            long_term_k=1,
            decision=decision,
            agent_emotion_info={},
            time_str=time_str,
            time_ctx=time_ctx,
        )
        self.assertEqual(prompt, "prompt:hi")
        self.assertEqual(runtime.generate_response(prompt), "reply:prompt:hi")
        self.assertEqual(runtime.split_double_text("one|two"), ["one", "two"])
        self.assertEqual(runtime.last_response_usage, {"prompt_tokens": 1, "completion_tokens": 2})

        runtime.append_turn_to_short_term_memory("u", "a")
        self.assertEqual(
            runtime.conversation_history,
            [{"role": "user", "text": "u"}, {"role": "ai", "text": "a"}],
        )

        runtime.reset_demo_long_term_memory()
        self.assertEqual(module.supabase.called_rpc, "reset_friend_memories_v2_to_demo_seed")

        runtime.record_turn("u", "a", True)
        self.assertEqual(module.recorded_turn, ("u", "a", True))

    def test_state_adapter_prefers_runtime_state_when_present(self) -> None:
        module = fake_module()
        module.runtime_state = SimpleNamespace(
            affinity=80,
            consecutive_negative=1,
            conversation_history=[{"role": "user", "text": "old"}],
            reset=lambda initial_affinity: None,
            last_response_usage={"prompt_tokens": 9, "completion_tokens": 1},
        )
        adapter = AIFriendStateAdapter(module)

        self.assertEqual(adapter.affinity, 80)
        adapter.affinity = 65
        adapter.consecutive_negative = 3
        adapter.append_turn("u", "a")

        self.assertEqual(module.runtime_state.affinity, 65)
        self.assertEqual(module.runtime_state.consecutive_negative, 3)
        self.assertEqual(
            module.runtime_state.conversation_history[-2:],
            [{"role": "user", "text": "u"}, {"role": "ai", "text": "a"}],
        )

    def test_runtime_uses_extracted_helpers_when_runtime_state_is_present(self) -> None:
        module = fake_native_module()
        runtime = AIFriendRuntime(module)

        memories = runtime.get_long_term_memory("hello", 2)
        time_str, time_ctx = runtime.consume_time_context_for_turn()
        decision = runtime.make_decision("hi", [], time_str, time_ctx)
        prompt = runtime.build_prompt(
            user_input="hi",
            long_term_memories=[{"description": "User finished homework.", "score": 1.0}],
            long_term_k=1,
            decision=decision,
            agent_emotion_info={"emotion": "neutral", "reason": ""},
            time_str=time_str,
            time_ctx=time_ctx,
        )
        response = runtime.generate_response(prompt)
        runtime.record_turn("hi", response, True)

        self.assertEqual(
            memories,
            [{"description": "repository memory for hello", "top_k": 2}],
        )
        self.assertEqual(
            module._memory_repository.recorded_turn,
            ("hi", "first. second.", True),
        )
        self.assertEqual(decision["timing"], "double_text")
        self.assertIn("User finished homework.", prompt)
        self.assertEqual(response, "first. second.")
        self.assertEqual(runtime.split_double_text(response), ["first", "second"])
        self.assertEqual(runtime.last_response_usage, {"prompt_tokens": 11, "completion_tokens": 7})

    def test_reset_drains_pending_memory_through_native_repository(self) -> None:
        module = fake_native_module()
        runtime = AIFriendRuntime(module)

        runtime.reset_state(initial_affinity=70)

        self.assertEqual(module._memory_repository.drain_count, 1)


if __name__ == "__main__":
    unittest.main()
