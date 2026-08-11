from __future__ import annotations

from fastapi import APIRouter, Depends

from application.dependencies import get_leaderboard_service
from application.services.leaderboard_service import LeaderboardService
from domain.games.leaderboard import GameId
from schemas.game_schema import LeaderboardEntryResponse, LeaderboardResponse


router = APIRouter()


@router.get("/leaderboards/{game_id}", response_model=LeaderboardResponse)
def get_leaderboard(
    game_id: GameId,
    service: LeaderboardService = Depends(get_leaderboard_service),
) -> LeaderboardResponse:
    is_match_history = game_id == GameId.MEMORY_MATCH
    entries = service.list_recent(game_id) if is_match_history else service.list(game_id)
    return LeaderboardResponse(
        game_id=game_id.value,
        view_mode="match_history" if is_match_history else "ranking",
        entries=[
            LeaderboardEntryResponse(
                rank=index + 1,
                player_name=entry.player_name,
                score=entry.score,
                detail=entry.detail,
                played_at=entry.played_at.isoformat(),
            )
            for index, entry in enumerate(entries)
        ],
    )
