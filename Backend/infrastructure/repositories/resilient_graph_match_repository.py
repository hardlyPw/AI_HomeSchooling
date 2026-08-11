from __future__ import annotations

import logging
import time

from domain.games.graph_match import GraphMatchSession
from domain.games.repository import GraphMatchRepository
from infrastructure.repositories.in_memory_graph_match_repository import (
    InMemoryGraphMatchRepository,
)


class ResilientGraphMatchRepository:
    """Writes to Supabase when available while keeping the live demo playable."""

    def __init__(
        self,
        remote: GraphMatchRepository,
        local: GraphMatchRepository | None = None,
    ) -> None:
        self._remote = remote
        self._local = local or InMemoryGraphMatchRepository()
        self._logger = logging.getLogger(__name__)
        self._retry_remote_at = 0.0

    def save(self, session: GraphMatchSession) -> None:
        self._local.save(session)
        if time.monotonic() < self._retry_remote_at:
            return
        try:
            self._remote.save(session)
        except Exception as exc:
            self._retry_remote_at = time.monotonic() + 60.0
            self._logger.warning("Graph Match Supabase save failed: %s", exc)

    def get(self, session_id: str) -> GraphMatchSession | None:
        local = self._local.get(session_id)
        if local is not None:
            return local
        if time.monotonic() < self._retry_remote_at:
            return None
        try:
            remote = self._remote.get(session_id)
        except Exception as exc:
            self._retry_remote_at = time.monotonic() + 60.0
            self._logger.warning("Graph Match Supabase load failed: %s", exc)
            return None
        if remote is not None:
            self._local.save(remote)
        return remote
