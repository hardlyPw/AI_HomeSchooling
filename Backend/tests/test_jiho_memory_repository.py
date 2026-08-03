from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
AGENT_ROOT = WORKSPACE_ROOT / "Agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from jiho_memory_repository import JihoMemoryRepository
from domain.agents.conversation import ModelInvocationConfig


class FakeVector:
    def tolist(self) -> list[float]:
        return [0.1, 0.2]


class FakeEmbeddingModel:
    def encode(self, text: str) -> FakeVector:
        self.last_text = text
        return FakeVector()


class FakeTable:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def insert(self, row: dict) -> "FakeTable":
        self.rows.append(row)
        return self

    def execute(self) -> None:
        return None


class FakeSupabase:
    def __init__(self) -> None:
        self.rpc_payload: dict | None = None
        self.table_instance = FakeTable()

    def rpc(self, name: str, payload: dict) -> SimpleNamespace:
        self.rpc_name = name
        self.rpc_payload = payload
        return SimpleNamespace(
            execute=lambda: SimpleNamespace(
                data=[
                    {
                        "description": "User finished math homework.",
                        "similarity": 0.9,
                        "poignancy": 4,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                    {
                        "description": "User mentioned lunch.",
                        "similarity": 0.1,
                        "poignancy": 2,
                        "created_at": datetime.now(timezone.utc).isoformat(),
                    },
                ]
            )
        )

    def table(self, name: str) -> FakeTable:
        self.table_name = name
        return self.table_instance


class FakeOpenAI:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content='{"entries":[{"description":"User completed homework.","poignancy":4}]}'
                            )
                        )
                    ]
                )
            )
        )


class JihoMemoryRepositoryTest(unittest.TestCase):
    def make_repository(self, enabled: bool = True) -> tuple[JihoMemoryRepository, FakeSupabase]:
        supabase = FakeSupabase()
        repository = JihoMemoryRepository(
            supabase_client=supabase,
            embedding_model=FakeEmbeddingModel(),
            openai_client=FakeOpenAI(),
            memory_table="memories",
            memory_match_rpc="match_memories",
            session_timeout_seconds=9999,
            uses_long_term_memory=lambda: enabled,
            extraction_model=ModelInvocationConfig(
                model="memory-model",
                temperature=0,
                max_tokens=1200,
            ),
        )
        return repository, supabase

    def test_get_long_term_memory_scores_and_limits_results(self) -> None:
        repository, supabase = self.make_repository()

        memories = repository.get_long_term_memory("math", top_k=1)

        self.assertEqual(supabase.rpc_name, "match_memories")
        self.assertEqual(supabase.rpc_payload["match_count"], 50)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0]["description"], "User finished math homework.")

    def test_record_turn_queues_and_flushes_on_session_break(self) -> None:
        repository, supabase = self.make_repository()

        repository.record_turn("u", "a", session_break=True)
        repository.shutdown()

        self.assertEqual(supabase.table_name, "memories")
        self.assertEqual(
            supabase.table_instance.rows[0]["description"],
            "User completed homework.",
        )
        self.assertEqual(repository.drain_pending_chunk(), [])

    def test_record_turn_noops_when_long_term_memory_disabled(self) -> None:
        repository, _ = self.make_repository(enabled=False)

        repository.record_turn("u", "a", session_break=True)

        self.assertEqual(repository.drain_pending_chunk(), [])


if __name__ == "__main__":
    unittest.main()
