from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType

AGENT_DIR = Path(__file__).resolve().parents[3] / "Agent"
if str(AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(AGENT_DIR))

from ai_friend_decision import make_decision as make_jiho_decision


class AIFriendDecisionClient:
    """Decision-layer gateway backed by extracted Jiho helpers when available."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    @property
    def _state(self):
        return getattr(self._module, "runtime_state", None)

    def consume_time_context_for_turn(self) -> tuple[str, str]:
        if self._state is not None:
            return self._state.time_context_tracker.consume_for_turn()
        return self._module._consume_time_context_for_turn()

    def make_decision(
        self,
        user_message: str,
        long_term_memory: list[dict],
        time_str: str,
        time_context: str,
    ) -> dict:
        if self._state is not None:
            result = make_jiho_decision(
                openai_client=self._module.openai_client,
                user_input=user_message,
                long_term_memories=long_term_memory,
                time_str=time_str,
                time_ctx=time_context,
                affinity=self._state.affinity,
                conversation_history=self._state.conversation_history,
                cooldown_until=self._state.cooldown_until,
                cooldown_reason=self._state.cooldown_reason,
                last_response_time=self._state.last_response_time,
            )
            self._state.cooldown_until = result.cooldown_until
            self._state.cooldown_reason = result.cooldown_reason
            return result.decision
        return self._module.make_decision(
            user_message,
            long_term_memory,
            time_str,
            time_context,
        )
