from __future__ import annotations

from domain.games.leaderboard import GameId, ScoreEntry
from domain.games.repository import ScoreRepository


class LeaderboardService:
    def __init__(self, repository: ScoreRepository) -> None:
        self._repository = repository

    def record(self, *, game_id: GameId, user_id: str, player_name: str, score: float, detail: str) -> ScoreEntry:
        entry = ScoreEntry(
            game_id=game_id,
            user_id=user_id,
            player_name=player_name,
            score=round(score, 1),
            detail=detail,
        )
        self._repository.save(entry)
        return entry

    def list(self, game_id: GameId, limit: int = 20) -> list[ScoreEntry]:
        return self._repository.list(game_id, limit)
