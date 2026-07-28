from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol


class FriendRuntime(Protocol):
    """Runtime operations required by the friend conversation service."""

    @property
    def affinity(self) -> int:
        raise NotImplementedError

    @affinity.setter
    def affinity(self, value: int) -> None:
        raise NotImplementedError

    @property
    def consecutive_negative(self) -> int:
        raise NotImplementedError

    @consecutive_negative.setter
    def consecutive_negative(self, value: int) -> None:
        raise NotImplementedError

    @property
    def conversation_history(self) -> list[dict]:
        raise NotImplementedError

    @property
    def uses_long_term_memory(self) -> bool:
        raise NotImplementedError

    @property
    def last_response_usage(self) -> dict | None:
        raise NotImplementedError

    def reset_state(self, initial_affinity: int) -> None:
        raise NotImplementedError

    def reset_demo_long_term_memory(self) -> None:
        raise NotImplementedError

    def get_long_term_memory(self, query_text: str, top_k: int) -> list[dict]:
        raise NotImplementedError

    def consume_time_context_for_turn(self) -> tuple[str, str | None]:
        raise NotImplementedError

    def make_decision(
        self,
        user_message: str,
        long_term_memory: list[dict],
        time_str: str,
        time_context: str | None,
    ) -> dict:
        raise NotImplementedError

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
        raise NotImplementedError

    def generate_response(self, prompt: str) -> str:
        raise NotImplementedError

    def split_double_text(self, response: str) -> list[str]:
        raise NotImplementedError

    def stream_response(self, prompt: str) -> Iterator:
        raise NotImplementedError

    def append_turn_to_short_term_memory(self, user_message: str, reply: str) -> None:
        raise NotImplementedError

    def record_turn(self, user_message: str, reply: str, session_break: bool) -> None:
        raise NotImplementedError
