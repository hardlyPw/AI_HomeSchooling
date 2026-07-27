from __future__ import annotations

from typing import Any, Iterator, Protocol


StreamEvent = dict[str, Any]


class ChatAgent(Protocol):
    @property
    def affinity(self) -> int:
        ...

    @property
    def history(self) -> list[dict]:
        ...

    def reset(self) -> None:
        ...

    def stream_reply(self, user_message: str) -> Iterator[StreamEvent]:
        ...


class DebuggableFriendAgent(ChatAgent, Protocol):
    def force_next_cooldown(self) -> None:
        ...

    def force_next_double_text(self) -> None:
        ...

    def end_cooldown(self) -> None:
        ...


class LessonTutor(Protocol):
    def stream_reply(
        self,
        user_message: str,
        conversation_history: list[dict] | None = None,
        current_video_time: float | None = None,
        figure_images: list[str] | None = None,
    ) -> Iterator[str]:
        ...
