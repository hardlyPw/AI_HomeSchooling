from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LessonChatInput:
    message: str
    pdf_context: str | None = None
    figure_context: str | None = None
    figure_images: list[str] | None = None
    current_video_time: float | None = None


@dataclass(frozen=True)
class ChatMessage:
    role: str
    text: str
