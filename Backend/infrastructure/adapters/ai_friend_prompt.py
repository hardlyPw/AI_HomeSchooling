from __future__ import annotations

from types import ModuleType


class AIFriendPromptBuilder:
    """Prompt-building gateway for the legacy AI_Friend module."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

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
        return self._module.build_prompt(
            user_input=user_input,
            long_term_memories=long_term_memories,
            long_term_k=long_term_k,
            decision=decision,
            agent_emotion_info=agent_emotion_info,
            time_str=time_str,
            time_ctx=time_ctx,
        )
