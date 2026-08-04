from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LessonTranscriptSection:
    timestamp_seconds: int
    timestamp_label: str
    content: str


class LessonTranscriptRepository(Protocol):
    def context_through(self, current_video_time: float | None) -> str | None:
        raise NotImplementedError
