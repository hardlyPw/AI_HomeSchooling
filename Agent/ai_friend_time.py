from __future__ import annotations

from collections.abc import Callable
from datetime import datetime


NOTEWORTHY_TIME_CONTEXTS = frozenset(
    {
        "early morning, getting ready for school",
        "school hours",
        "late for a 7th grader",
        "middle of the night",
    }
)


class TimeContextTracker:
    """Tracks per-session time buckets so Jiho does not repeat the same cue."""

    def __init__(self, now_provider: Callable[[], datetime] = datetime.now) -> None:
        self._now_provider = now_provider
        self._seen_buckets: set[str] = set()

    def get_time_context(self) -> tuple[str, str]:
        now = self._now_provider()
        time_str = now.strftime("%I:%M %p")
        hour = now.hour
        if 6 <= hour < 8:
            context = "early morning, getting ready for school"
        elif 8 <= hour < 15:
            context = "school hours"
        elif 15 <= hour < 18:
            context = "after school, free time"
        elif 18 <= hour < 21:
            context = "evening at home"
        elif 21 <= hour < 24:
            context = "late for a 7th grader"
        else:
            context = "middle of the night"
        return time_str, context

    def consume_for_turn(self) -> tuple[str, str | None]:
        time_str, context = self.get_time_context()
        if context in NOTEWORTHY_TIME_CONTEXTS:
            if context in self._seen_buckets:
                return time_str, None
            self._seen_buckets.add(context)
        return time_str, context

    def reset(self) -> None:
        self._seen_buckets.clear()
