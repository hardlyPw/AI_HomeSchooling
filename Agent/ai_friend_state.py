from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ai_friend_time import TimeContextTracker


@dataclass
class JihoRuntimeState:
    """Mutable runtime state for the legacy Jiho friend runtime."""

    affinity: int = 70
    consecutive_negative: int = 0
    conversation_history: list[dict] = field(default_factory=list)
    cooldown_until: datetime | None = None
    cooldown_reason: str = ""
    last_response_time: datetime = field(default_factory=datetime.now)
    last_response_usage: dict | None = None
    time_context_tracker: TimeContextTracker = field(default_factory=TimeContextTracker)

    def reset(self, initial_affinity: int = 70) -> None:
        self.affinity = initial_affinity
        self.consecutive_negative = 0
        self.conversation_history.clear()
        self.cooldown_until = None
        self.cooldown_reason = ""
        self.last_response_time = datetime.now()
        self.last_response_usage = None
        self.time_context_tracker.reset()

    def add_message(self, role: str, text: str) -> None:
        self.conversation_history.append({"role": role, "text": text})
