from __future__ import annotations

from datetime import datetime

from domain.games.leaderboard import GameId, ScoreEntry


class SupabaseScoreRepository:
    def __init__(self, client) -> None:
        self._client = client

    def save(self, entry: ScoreEntry) -> None:
        self._client.table("game_leaderboard_scores").upsert(
            {
                "id": entry.id,
                "game_id": entry.game_id.value,
                "user_id": entry.user_id,
                "player_name": entry.player_name,
                "score": entry.score,
                "detail": entry.detail,
                "played_at": entry.played_at.isoformat(),
            },
            on_conflict="id",
        ).execute()

    def list(self, game_id: GameId, limit: int = 20) -> list[ScoreEntry]:
        response = (
            self._client.table("game_leaderboard_scores")
            .select("*")
            .eq("game_id", game_id.value)
            .order("score", desc=True)
            .limit(limit)
            .execute()
        )
        return [
            ScoreEntry(
                id=row["id"],
                game_id=GameId(row["game_id"]),
                user_id=row["user_id"],
                player_name=row["player_name"],
                score=float(row["score"]),
                detail=row["detail"],
                played_at=datetime.fromisoformat(row["played_at"].replace("Z", "+00:00")),
            )
            for row in response.data or []
        ]
