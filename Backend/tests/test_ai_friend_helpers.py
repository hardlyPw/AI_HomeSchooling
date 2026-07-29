from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = WORKSPACE_ROOT / "Agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from ai_friend_decision import make_decision
from ai_friend_decision import normalize_decision
from ai_friend_response import generate_response
from ai_friend_response import split_double_text
from ai_friend_time import TimeContextTracker


class FakeCompletions:
    def __init__(self, content: str, *, raise_error: bool = False) -> None:
        self.content = content
        self.raise_error = raise_error

    def create(self, **kwargs):
        if self.raise_error:
            raise RuntimeError("boom")
        message = SimpleNamespace(content=self.content)
        choice = SimpleNamespace(message=message)
        usage = SimpleNamespace(prompt_tokens=3, completion_tokens=4)
        return SimpleNamespace(choices=[choice], usage=usage)


class FakeOpenAIClient:
    def __init__(self, content: str, *, raise_error: bool = False) -> None:
        self.chat = SimpleNamespace(
            completions=FakeCompletions(content, raise_error=raise_error)
        )


class AIFriendHelpersTest(unittest.TestCase):
    def test_time_context_suppresses_repeated_noteworthy_bucket(self) -> None:
        tracker = TimeContextTracker(lambda: datetime(2026, 7, 29, 22, 15))

        self.assertEqual(tracker.consume_for_turn(), ("10:15 PM", "late for a 7th grader"))
        self.assertEqual(tracker.consume_for_turn(), ("10:15 PM", None))

        tracker.reset()
        self.assertEqual(tracker.consume_for_turn(), ("10:15 PM", "late for a 7th grader"))

    def test_normalize_decision_clamps_invalid_fields(self) -> None:
        decision = normalize_decision(
            {
                "timing": "weird",
                "action": "strange",
                "session_break": "",
                "affinity_delta": "99",
                "affinity_reason": 3,
            }
        )

        self.assertEqual(decision["timing"], "instant")
        self.assertEqual(decision["action"], "normal")
        self.assertFalse(decision["session_break"])
        self.assertEqual(decision["affinity_delta"], 10)
        self.assertEqual(decision["affinity_reason"], "")

    def test_make_decision_returns_fallback_on_client_error(self) -> None:
        client = FakeOpenAIClient("", raise_error=True)

        result = make_decision(
            openai_client=client,
            user_input="hi",
            long_term_memories=[],
            time_str="10:00 PM",
            time_ctx=None,
            affinity=70,
            conversation_history=[],
            cooldown_until=None,
            cooldown_reason="",
            last_response_time=datetime(2026, 7, 29, 22, 0),
        )

        self.assertEqual(result.decision["timing"], "instant")
        self.assertEqual(result.decision["action"], "normal")
        self.assertFalse(result.decision["session_break"])

    def test_generate_response_returns_text_and_usage(self) -> None:
        client = FakeOpenAIClient("yo")

        text, usage = generate_response(client, "prompt")

        self.assertEqual(text, "yo")
        self.assertEqual(usage, {"prompt_tokens": 3, "completion_tokens": 4})

    def test_split_double_text_caps_at_two_messages(self) -> None:
        self.assertEqual(split_double_text("one. two. three."), ["one", "two. three"])
        self.assertEqual(split_double_text("one two three four"), ["one two", "three four"])


if __name__ == "__main__":
    unittest.main()
