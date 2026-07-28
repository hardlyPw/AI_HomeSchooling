from __future__ import annotations

from types import ModuleType


class AIFriendStateAdapter:
    """State gateway for the legacy AI_Friend module globals."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    @property
    def affinity(self) -> int:
        return self._module.affinity

    @affinity.setter
    def affinity(self, value: int) -> None:
        self._module.affinity = value

    @property
    def consecutive_negative(self) -> int:
        return self._module.consecutive_negative

    @consecutive_negative.setter
    def consecutive_negative(self, value: int) -> None:
        self._module.consecutive_negative = value

    @property
    def conversation_history(self) -> list[dict]:
        return self._module.conversation_history

    def reset(self, initial_affinity: int) -> None:
        self._module.conversation_history.clear()
        self._module.affinity = initial_affinity
        self._module.consecutive_negative = 0
        self._module._cooldown_until = None
        self._module._cooldown_reason = ""
        self.drain_pending_chunk()

    def drain_pending_chunk(self) -> None:
        drain_pending = getattr(self._module, "_drain_pending_chunk", None)
        if callable(drain_pending):
            drain_pending()

    def append_turn(self, user_message: str, reply: str) -> None:
        self._module.conversation_history.append({"role": "user", "text": user_message})
        self._module.conversation_history.append({"role": "ai", "text": reply})
