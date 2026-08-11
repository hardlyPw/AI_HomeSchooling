from __future__ import annotations

from fastapi import APIRouter, Depends, Header, status

from api.v1.game_routes.common import handle_game_error, user_id
from application.dependencies import get_graph_challenge_service
from application.services.graph_challenge_service import GraphChallengeService
from domain.games.graph_challenge import expression_points
from schemas.game_schema import (
    GraphChallengeAttemptResponse,
    GraphChallengeResponse,
    GraphChallengeRoundResponse,
    GraphPoint,
    StartGraphChallengeRequest,
    SubmitGraphExpressionRequest,
)


router = APIRouter()


def _round_response(round_state, *, reveal: bool) -> GraphChallengeRoundResponse:
    attempt = round_state.attempt
    return GraphChallengeRoundResponse(
        number=round_state.number,
        family=round_state.target.family,
        target_points=[
            GraphPoint(x=x, y=y)
            for x, y in expression_points(round_state.target.expression)
        ],
        target_latex=round_state.target.latex if reveal else None,
        attempt=(
            GraphChallengeAttemptResponse(
                expression=attempt.expression,
                graph_score=attempt.graph_score,
                time_bonus=attempt.time_bonus,
                score=attempt.score,
                elapsed_ms=attempt.elapsed_ms,
            )
            if attempt
            else None
        ),
        completed=round_state.completed,
    )


def _response(session) -> GraphChallengeResponse:
    return GraphChallengeResponse(
        id=session.id,
        player_name=session.player_name,
        round_count=len(session.rounds),
        current_round=_round_response(session.current_round, reveal=session.current_round.completed),
        rounds=[
            _round_response(round_state, reveal=round_state.completed)
            for round_state in session.rounds
        ],
        total_score=session.total_score,
        completed=session.completed,
    )


@router.post(
    "/graph-challenge/sessions",
    response_model=GraphChallengeResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_graph_challenge(
    request: StartGraphChallengeRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: GraphChallengeService = Depends(get_graph_challenge_service),
) -> GraphChallengeResponse:
    return _response(service.start(user_id=user_id(x_user_id), player_name=request.player_name))


@router.post(
    "/graph-challenge/sessions/{session_id}/attempts",
    response_model=GraphChallengeResponse,
)
def submit_graph_expression(
    session_id: str,
    request: SubmitGraphExpressionRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: GraphChallengeService = Depends(get_graph_challenge_service),
) -> GraphChallengeResponse:
    try:
        return _response(
            service.submit(
                session_id,
                user_id=user_id(x_user_id),
                expression=request.expression,
                elapsed_ms=request.elapsed_ms,
            )
        )
    except Exception as exc:
        handle_game_error(exc)


@router.post(
    "/graph-challenge/sessions/{session_id}/advance",
    response_model=GraphChallengeResponse,
)
def advance_graph_challenge(
    session_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: GraphChallengeService = Depends(get_graph_challenge_service),
) -> GraphChallengeResponse:
    try:
        return _response(service.advance(session_id, user_id=user_id(x_user_id)))
    except Exception as exc:
        handle_game_error(exc)
