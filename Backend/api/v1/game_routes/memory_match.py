from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status

from api.v1.game_routes.common import handle_game_error, user_id
from application.dependencies import get_memory_match_service
from application.services.memory_match_service import MemoryMatchService
from domain.games.memory_match import PREVIEW_SECONDS, TURN_SECONDS
from schemas.game_schema import (
    AgentCardTurnResponse,
    MemoryCardResponse,
    MemoryMatchResponse,
    PlayMemoryCardsRequest,
    StartMemoryMatchRequest,
)


router = APIRouter()


def _response(session) -> MemoryMatchResponse:
    reveal_all = session.phase == "preview"
    return MemoryMatchResponse(
        id=session.id,
        agent_id=session.agent_id,
        agent_name=session.agent_name,
        agent_skill=session.agent_skill.value,
        phase=session.phase,
        cards=[
            MemoryCardResponse(
                index=index,
                value=value if reveal_all or index in session.matched_indices else None,
                matched=index in session.matched_indices,
            )
            for index, value in enumerate(session.board)
        ],
        user_score=session.user_score,
        agent_score=session.agent_score,
        winner=session.winner,
        preview_seconds=PREVIEW_SECONDS,
        turn_seconds=TURN_SECONDS,
        agent_turns=[
            AgentCardTurnResponse(
                indices=turn.indices,
                values=turn.values,
                matched=turn.matched,
                score_after=turn.score_after,
            )
            for turn in session.last_agent_turns
        ],
    )


@router.post(
    "/memory-match/sessions",
    response_model=MemoryMatchResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_memory_match(
    request: StartMemoryMatchRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: MemoryMatchService = Depends(get_memory_match_service),
) -> MemoryMatchResponse:
    try:
        return _response(
            service.start(
                user_id=user_id(x_user_id),
                agent_id=request.agent_id,
                player_name=request.player_name,
            )
        )
    except Exception as exc:
        handle_game_error(exc)


@router.post("/memory-match/sessions/{session_id}/ready", response_model=MemoryMatchResponse)
def ready_memory_match(
    session_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: MemoryMatchService = Depends(get_memory_match_service),
) -> MemoryMatchResponse:
    try:
        return _response(service.ready(session_id, user_id=user_id(x_user_id)))
    except Exception as exc:
        handle_game_error(exc)


@router.post("/memory-match/sessions/{session_id}/play", response_model=MemoryMatchResponse)
def play_memory_match(
    session_id: str,
    request: PlayMemoryCardsRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: MemoryMatchService = Depends(get_memory_match_service),
) -> MemoryMatchResponse:
    try:
        return _response(
            service.play(
                session_id,
                user_id=user_id(x_user_id),
                indices=request.indices,
            )
        )
    except Exception as exc:
        handle_game_error(exc)


@router.post("/memory-match/sessions/{session_id}/pass", response_model=MemoryMatchResponse)
def pass_memory_match(
    session_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: MemoryMatchService = Depends(get_memory_match_service),
) -> MemoryMatchResponse:
    try:
        return _response(service.pass_turn(session_id, user_id=user_id(x_user_id)))
    except Exception as exc:
        handle_game_error(exc)
