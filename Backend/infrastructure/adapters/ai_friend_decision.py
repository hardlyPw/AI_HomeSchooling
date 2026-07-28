from __future__ import annotations

from types import ModuleType


class AIFriendDecisionClient:
    """Decision-layer gateway for the legacy AI_Friend module."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    def consume_time_context_for_turn(self) -> tuple[str, str]:
        return self._module._consume_time_context_for_turn()

    def make_decision(
        self,
        user_message: str,
        long_term_memory: list[dict],
        time_str: str,
        time_context: str,
    ) -> dict:
        return self._module.make_decision(
            user_message,
            long_term_memory,
            time_str,
            time_context,
        )
