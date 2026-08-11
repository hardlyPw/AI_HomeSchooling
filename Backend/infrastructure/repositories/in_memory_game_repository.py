from __future__ import annotations

import threading

from domain.games.graph_challenge import GraphChallengeSession
from domain.games.leaderboard import GameId, ScoreEntry
from domain.games.memory_match import MemoryMatchSession


class InMemoryGraphChallengeRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, GraphChallengeSession] = {}
        self._lock = threading.RLock()

    def save(self, session: GraphChallengeSession) -> None:
        with self._lock:
            self._sessions[session.id] = session

    def get(self, session_id: str) -> GraphChallengeSession | None:
        with self._lock:
            return self._sessions.get(session_id)


class InMemoryMemoryMatchRepository:
    def __init__(self) -> None:
        self._sessions: dict[str, MemoryMatchSession] = {}
        self._lock = threading.RLock()

    def save(self, session: MemoryMatchSession) -> None:
        with self._lock:
            self._sessions[session.id] = session

    def get(self, session_id: str) -> MemoryMatchSession | None:
        with self._lock:
            return self._sessions.get(session_id)


class InMemoryScoreRepository:
    def __init__(self) -> None:
        self._entries: list[ScoreEntry] = []
        self._lock = threading.RLock()

    def save(self, entry: ScoreEntry) -> None:
        with self._lock:
            if not any(item.id == entry.id for item in self._entries):
                self._entries.append(entry)

    def list(self, game_id: GameId, limit: int = 20) -> list[ScoreEntry]:
        with self._lock:
            entries = [item for item in self._entries if item.game_id == game_id]
            return sorted(entries, key=lambda item: (-item.score, item.played_at))[:limit]

    def list_recent(self, game_id: GameId, limit: int = 20) -> list[ScoreEntry]:
        with self._lock:
            entries = [item for item in self._entries if item.game_id == game_id]
            return sorted(entries, key=lambda item: item.played_at, reverse=True)[:limit]
