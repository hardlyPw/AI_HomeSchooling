from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import tempfile
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = WORKSPACE_ROOT / "Agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from ai_friend_eval import export_to_jsonl
from ai_friend_eval import update_affinity


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.last_request: dict | None = None

    def create(self, **kwargs):
        self.last_request = kwargs
        message = SimpleNamespace(content=self.content)
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(choices=[choice])


class FakeOpenAIClient:
    def __init__(self, content: str) -> None:
        self.completions = FakeCompletions(content)
        self.chat = SimpleNamespace(completions=self.completions)


class AIFriendEvalTest(unittest.TestCase):
    def test_update_affinity_parses_and_clamps_delta(self) -> None:
        client = FakeOpenAIClient('{"delta": 99, "reason": "too much"}')

        delta, reason = update_affinity(
            openai_client=client,
            role_display={"user": "User", "ai": "Jiho"},
            conversation_history=[
                {"role": "user", "text": "hi"},
                {"role": "ai", "text": "yo"},
            ],
            current_affinity=70,
            agent_emotion_info={"emotion": "neutral", "reason": "steady"},
            user_input="new phone",
            ai_reply="okay",
        )

        self.assertEqual(delta, 10)
        self.assertEqual(reason, "too much")
        self.assertEqual(client.completions.last_request["response_format"], {"type": "json_object"})

    def test_export_to_jsonl_writes_autorater_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            export_path = Path(temp_dir) / "autorater.jsonl"

            export_to_jsonl(
                user_input="hello",
                ai_reply="yo",
                affinity_at_response=61,
                consecutive_neg=2,
                agent_emotion_info={"emotion": "amused"},
                export_file=str(export_path),
            )

            line = export_path.read_text(encoding="utf-8").strip()
            record = json.loads(line)

        self.assertTrue(record["id"].startswith("ai_friend_"))
        self.assertEqual(record["input"], "hello")
        self.assertIn("affinity=61", record["context"])
        self.assertIn("consecutive_negative=2", record["context"])
        self.assertIn("agent_emotion=amused", record["context"])
        self.assertEqual(record["messages"][1], {"role": "assistant", "content": "yo"})


if __name__ == "__main__":
    unittest.main()
