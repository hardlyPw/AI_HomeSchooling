from __future__ import annotations

import threading

from domain.games.graph_match import GraphMatchSession


class InMemoryGraphMatchRepository:
    """Single-process game storage replaceable by a database repository."""

    def __init__(self) -> None:
        self._sessions: dict[str, GraphMatchSession] = {}
        self._lock = threading.RLock()

    def save(self, session: GraphMatchSession) -> None:
        with self._lock:
            self._sessions[session.id] = session

    def get(self, session_id: str) -> GraphMatchSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def completed_sessions(self) -> tuple[GraphMatchSession, ...]:
        with self._lock:
            return tuple(session for session in self._sessions.values() if session.completed)
