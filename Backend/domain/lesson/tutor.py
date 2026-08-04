from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol


class LessonTutorClient(Protocol):
    def stream_reply(self, messages: list[dict[str, Any]]) -> Iterator[str]:
        raise NotImplementedError
