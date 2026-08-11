from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


class GameId(str, Enum):
    GRAPH_CHALLENGE = "graph_challenge"
    MEMORY_MATCH = "memory_match"


@dataclass(frozen=True)
class ScoreEntry:
    game_id: GameId
    user_id: str
    player_name: str
    score: float
    detail: str
    played_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: uuid4().hex)
