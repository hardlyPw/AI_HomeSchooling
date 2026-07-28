from __future__ import annotations

from collections.abc import Iterator
from types import ModuleType

from infrastructure.adapters.ai_friend_decision import AIFriendDecisionClient
from infrastructure.adapters.ai_friend_memory import AIFriendMemoryRepository
from infrastructure.adapters.ai_friend_module import load_ai_friend_module
from infrastructure.adapters.ai_friend_prompt import AIFriendPromptBuilder
from infrastructure.adapters.ai_friend_response import AIFriendResponseGenerator
from infrastructure.adapters.ai_friend_state import AIFriendStateAdapter


class AIFriendRuntime:
    """Facade that composes focused adapters around Agent/AI_Friend.py."""

    def __init__(self, module: ModuleType | None = None) -> None:
        legacy_module = module or load_ai_friend_module()
        self._state = AIFriendStateAdapter(legacy_module)
        self._memory = AIFriendMemoryRepository(legacy_module)
        self._decision = AIFriendDecisionClient(legacy_module)
        self._prompt = AIFriendPromptBuilder(legacy_module)
        self._response = AIFriendResponseGenerator(legacy_module)

    @property
    def affinity(self) -> int:
        return self._state.affinity

    @affinity.setter
    def affinity(self, value: int) -> None:
        self._state.affinity = value

    @property
    def consecutive_negative(self) -> int:
        return self._state.consecutive_negative

    @consecutive_negative.setter
    def consecutive_negative(self, value: int) -> None:
        self._state.consecutive_negative = value

    @property
    def conversation_history(self) -> list[dict]:
        return self._state.conversation_history

    @property
    def uses_long_term_memory(self) -> bool:
        return self._memory.uses_long_term_memory

    @property
    def last_response_usage(self) -> dict | None:
        return self._response.last_response_usage

    def reset_state(self, initial_affinity: int) -> None:
        self._state.reset(initial_affinity)

    def reset_demo_long_term_memory(self) -> None:
        self._memory.reset_demo_long_term_memory()

    def get_long_term_memory(self, query_text: str, top_k: int) -> list[dict]:
        return self._memory.get_long_term_memory(query_text, top_k)

    def consume_time_context_for_turn(self) -> tuple[str, str]:
        return self._decision.consume_time_context_for_turn()

    def make_decision(
        self,
        user_message: str,
        long_term_memory: list[dict],
        time_str: str,
        time_context: str,
    ) -> dict:
        return self._decision.make_decision(
            user_message,
            long_term_memory,
            time_str,
            time_context,
        )

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
        return self._prompt.build_prompt(
            user_input=user_input,
            long_term_memories=long_term_memories,
            long_term_k=long_term_k,
            decision=decision,
            agent_emotion_info=agent_emotion_info,
            time_str=time_str,
            time_ctx=time_ctx,
        )

    def generate_response(self, prompt: str) -> str:
        return self._response.generate_response(prompt)

    def split_double_text(self, response: str) -> list[str]:
        return self._response.split_double_text(response)

    def stream_response(self, prompt: str) -> Iterator:
        return self._response.stream_response(prompt)

    def append_turn_to_short_term_memory(self, user_message: str, reply: str) -> None:
        self._state.append_turn(user_message, reply)

    def record_turn(self, user_message: str, reply: str, session_break: bool) -> None:
        self._memory.record_turn(user_message, reply, session_break)
