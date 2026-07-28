from __future__ import annotations

from types import ModuleType


class AIFriendMemoryRepository:
    """Memory gateway for the legacy AI_Friend module."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    @property
    def uses_long_term_memory(self) -> bool:
        return self._module.USE_LONG_TERM_MEMORY

    def reset_demo_long_term_memory(self) -> None:
        self._module.supabase.rpc("reset_friend_memories_v2_to_demo_seed", {}).execute()

    def get_long_term_memory(self, query_text: str, top_k: int) -> list[dict]:
        return self._module.get_long_term_memory(query_text, top_k=top_k)

    def record_turn(self, user_message: str, reply: str, session_break: bool) -> None:
        self._module.record_turn(user_message, reply, session_break=session_break)
