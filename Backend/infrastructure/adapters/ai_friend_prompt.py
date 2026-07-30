from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

AGENT_DIR = Path(__file__).resolve().parents[3] / "Agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from ai_friend_prompt_builder import build_runtime_prompt


class AIFriendPromptBuilder:
    """Prompt-building gateway backed by extracted Jiho helpers when available."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    @property
    def _state(self):
        return getattr(self._module, "runtime_state", None)

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
        if self._state is not None:
            return build_runtime_prompt(
                user_input=user_input,
                affinity=self._state.affinity,
                conversation_history=self._state.conversation_history,
                memory_loader=self._module.get_long_term_memory,
                time_context_loader=self._state.time_context_tracker.get_time_context,
                agent_emotion_info=agent_emotion_info,
                long_term_memories=long_term_memories,
                long_term_k=long_term_k,
                decision=decision,
                time_str=time_str,
                time_ctx=time_ctx,
                debug_prompt=getattr(self._module, "DEBUG_PROMPT", False),
            )
        return self._module.build_prompt(
            user_input=user_input,
            long_term_memories=long_term_memories,
            long_term_k=long_term_k,
            decision=decision,
            agent_emotion_info=agent_emotion_info,
            time_str=time_str,
            time_ctx=time_ctx,
        )
