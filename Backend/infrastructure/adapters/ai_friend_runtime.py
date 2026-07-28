from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterator

_AGENT_DIR = Path(__file__).resolve().parents[3] / "Agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

import AI_Friend as af  # noqa: E402


class AIFriendRuntime:
    """Infrastructure adapter around the legacy Agent/AI_Friend.py module."""

    def __init__(self) -> None:
        af.DEBUG_PROMPT = False

    @property
    def affinity(self) -> int:
        return af.affinity

    @affinity.setter
    def affinity(self, value: int) -> None:
        af.affinity = value

    @property
    def consecutive_negative(self) -> int:
        return af.consecutive_negative

    @consecutive_negative.setter
    def consecutive_negative(self, value: int) -> None:
        af.consecutive_negative = value

    @property
    def conversation_history(self) -> list[dict]:
        return af.conversation_history

    @property
    def uses_long_term_memory(self) -> bool:
        return af.USE_LONG_TERM_MEMORY

    @property
    def last_response_usage(self) -> dict | None:
        return getattr(af, "last_response_usage", None)

    def reset_state(self, initial_affinity: int) -> None:
        af.conversation_history.clear()
        af.affinity = initial_affinity
        af.consecutive_negative = 0
        af._cooldown_until = None
        af._cooldown_reason = ""
        self.drain_pending_chunk()

    def drain_pending_chunk(self) -> None:
        drain_pending = getattr(af, "_drain_pending_chunk", None)
        if callable(drain_pending):
            drain_pending()

    def reset_demo_long_term_memory(self) -> None:
        af.supabase.rpc("reset_friend_memories_v2_to_demo_seed", {}).execute()

    def get_long_term_memory(self, query_text: str, top_k: int) -> list[dict]:
        return af.get_long_term_memory(query_text, top_k=top_k)

    def consume_time_context_for_turn(self) -> tuple[str, str]:
        return af._consume_time_context_for_turn()

    def make_decision(
        self,
        user_message: str,
        long_term_memory: list[dict],
        time_str: str,
        time_context: str,
    ) -> dict:
        return af.make_decision(user_message, long_term_memory, time_str, time_context)

    def build_prompt(
        self,
        *,
        user_input: str,
        long_term_memories: list[dict],
        long_term_k: int,
        decision: dict,
        agent_emotion_info: dict,
        time_str: str,
        time_ctx: str,
    ) -> str:
        return af.build_prompt(
            user_input=user_input,
            long_term_memories=long_term_memories,
            long_term_k=long_term_k,
            decision=decision,
            agent_emotion_info=agent_emotion_info,
            time_str=time_str,
            time_ctx=time_ctx,
        )

    def generate_response(self, prompt: str) -> str:
        return af.generate_ai_response(prompt)

    def split_double_text(self, response: str) -> list[str]:
        return af._split_double_text(response)

    def stream_response(self, prompt: str) -> Iterator:
        return af.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
            stream=True,
            stream_options={"include_usage": True},
        )

    def append_turn_to_short_term_memory(self, user_message: str, reply: str) -> None:
        af.conversation_history.append({"role": "user", "text": user_message})
        af.conversation_history.append({"role": "ai", "text": reply})

    def record_turn(self, user_message: str, reply: str, session_break: bool) -> None:
        af.record_turn(user_message, reply, session_break=session_break)
