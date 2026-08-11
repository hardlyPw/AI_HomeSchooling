from __future__ import annotations

from typing import Protocol

from domain.games.graph_match import GraphMatchSession
from domain.games.graph_challenge import GraphChallengeSession
from domain.games.leaderboard import GameId, ScoreEntry
from domain.games.memory_match import MemoryMatchSession


class GraphMatchRepository(Protocol):
    def save(self, session: GraphMatchSession) -> None: ...

    def get(self, session_id: str) -> GraphMatchSession | None: ...


class GameActivityMemory(Protocol):
    def record(self, session: GraphMatchSession) -> tuple[str, ...]: ...


class GraphChallengeRepository(Protocol):
    def save(self, session: GraphChallengeSession) -> None: ...

    def get(self, session_id: str) -> GraphChallengeSession | None: ...


class MemoryMatchRepository(Protocol):
    def save(self, session: MemoryMatchSession) -> None: ...

    def get(self, session_id: str) -> MemoryMatchSession | None: ...


class ScoreRepository(Protocol):
    def save(self, entry: ScoreEntry) -> None: ...

    def list(self, game_id: GameId, limit: int = 20) -> list[ScoreEntry]: ...

    def list_recent(self, game_id: GameId, limit: int = 20) -> list[ScoreEntry]: ...
