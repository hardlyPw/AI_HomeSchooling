from __future__ import annotations

import logging
import time

from domain.games.leaderboard import GameId, ScoreEntry
from domain.games.repository import ScoreRepository
from infrastructure.repositories.in_memory_game_repository import InMemoryScoreRepository


class ResilientScoreRepository:
    def __init__(self, remote: ScoreRepository, local: ScoreRepository | None = None) -> None:
        self._remote = remote
        self._local = local or InMemoryScoreRepository()
        self._retry_remote_at = 0.0
        self._logger = logging.getLogger(__name__)

    def save(self, entry: ScoreEntry) -> None:
        self._local.save(entry)
        if time.monotonic() < self._retry_remote_at:
            return
        try:
            self._remote.save(entry)
        except Exception as exc:
            self._retry_remote_at = time.monotonic() + 60
            self._logger.warning("Leaderboard Supabase save failed: %s", exc)

    def list(self, game_id: GameId, limit: int = 20) -> list[ScoreEntry]:
        return self._load(game_id, limit, recent=False)

    def list_recent(self, game_id: GameId, limit: int = 20) -> list[ScoreEntry]:
        return self._load(game_id, limit, recent=True)

    def _load(self, game_id: GameId, limit: int, *, recent: bool) -> list[ScoreEntry]:
        local = self._local.list_recent(game_id, limit) if recent else self._local.list(game_id, limit)
        if time.monotonic() < self._retry_remote_at:
            return local
        try:
            remote = self._remote.list_recent(game_id, limit) if recent else self._remote.list(game_id, limit)
        except Exception as exc:
            self._retry_remote_at = time.monotonic() + 60
            self._logger.warning("Leaderboard Supabase load failed: %s", exc)
            return local
        merged = {entry.id: entry for entry in [*remote, *local]}
        if recent:
            return sorted(merged.values(), key=lambda item: item.played_at, reverse=True)[:limit]
        return sorted(merged.values(), key=lambda item: (-item.score, item.played_at))[:limit]
