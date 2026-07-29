from __future__ import annotations

from types import ModuleType


class AIFriendStateAdapter:
    """State gateway for the legacy AI_Friend module globals."""

    def __init__(self, module: ModuleType) -> None:
        self._module = module

    @property
    def _state(self):
        return getattr(self._module, "runtime_state", self._module)

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

    def reset(self, initial_affinity: int) -> None:
        if hasattr(self._state, "reset"):
            self._state.reset(initial_affinity)
        else:
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
        self.conversation_history.append({"role": "user", "text": user_message})
        self.conversation_history.append({"role": "ai", "text": reply})
