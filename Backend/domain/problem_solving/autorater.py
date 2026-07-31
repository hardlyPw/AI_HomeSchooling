from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AutoraterStartResult:
    opener: str
    total_problems: int
    mode: str | None = None


@dataclass(frozen=True)
class AutoraterChatResult:
    reply: str
    next_opener: str | None
    mode: str | None
    next_mode: str | None
    is_done: bool
