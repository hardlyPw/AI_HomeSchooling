from __future__ import annotations

from typing import Protocol

from domain.games.graph_match import GraphMatchSession


class GraphMatchRepository(Protocol):
    def save(self, session: GraphMatchSession) -> None: ...

    def get(self, session_id: str) -> GraphMatchSession | None: ...


class GameActivityMemory(Protocol):
    def record(self, session: GraphMatchSession) -> tuple[str, ...]: ...
