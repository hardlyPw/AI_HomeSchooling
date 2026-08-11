from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status

from application.dependencies import get_graph_match_service
from application.services.agent_catalog_service import AgentNotFoundError
from application.services.graph_match_service import (
    GraphMatchNotFoundError,
    GraphMatchService,
    GraphMatchStateError,
)
from domain.games.graph_match import GraphFunction, MAX_ATTEMPTS, QuickChat
from schemas.game_schema import (
    GraphAttemptResponse,
    GraphMatchResponse,
    GraphPoint,
    GraphRoundResponse,
    QuickChatEventResponse,
    QuickChatRequest,
    StartGraphMatchRequest,
    SubmitGraphAttemptRequest,
)


router = APIRouter()


def _user_id(value: str | None) -> str:
    return (value or "demo-user").strip() or "demo-user"


def _points(function) -> list[GraphPoint]:
    return [GraphPoint(x=x, y=y) for x, y in function.points()]


def _to_response(session) -> GraphMatchResponse:
    if session.user_total_score > session.agent_total_score:
        overall_winner = "user"
    elif session.user_total_score < session.agent_total_score:
        overall_winner = "agent"
    else:
        overall_winner = "draw"
    return GraphMatchResponse(
        id=session.id,
        agent_id=session.agent_id,
        agent_name=session.agent_name,
        agent_skill=session.agent_skill.value,
        round_count=len(session.rounds),
        current_round=_to_round_response(session.current_round),
        rounds=[_to_round_response(round_state) for round_state in session.rounds],
        user_round_wins=session.user_round_wins,
        agent_round_wins=session.agent_round_wins,
        user_total_score=session.user_total_score,
        agent_total_score=session.agent_total_score,
        completed=session.completed,
        overall_winner=overall_winner if session.completed else None,
        quick_chats=[
            QuickChatEventResponse(sender=event.sender, chat=event.chat.value, text=event.text)
            for event in session.quick_chats[-6:]
        ],
    )


def _to_round_response(round_state) -> GraphRoundResponse:
    return GraphRoundResponse(
        number=round_state.number,
        target_points=_points(round_state.target),
        attempts=[
            GraphAttemptResponse(
                latex=attempt.function.to_latex(),
                graph_score=attempt.graph_score,
                time_bonus=attempt.time_bonus,
                score=attempt.score,
                elapsed_ms=attempt.elapsed_ms,
            )
            for attempt in round_state.attempts
        ],
        attempts_remaining=MAX_ATTEMPTS - len(round_state.attempts),
        completed=round_state.completed,
        target_latex=round_state.target.to_latex() if round_state.completed else None,
        agent_latex=round_state.agent_guess.to_latex() if round_state.agent_guess else None,
        agent_points=_points(round_state.agent_guess) if round_state.agent_guess else [],
        agent_graph_score=round_state.agent_graph_score,
        agent_time_bonus=round_state.agent_time_bonus,
        agent_score=round_state.agent_score,
        agent_elapsed_ms=round_state.agent_elapsed_ms,
        winner=round_state.winner,
    )


def _handle_game_error(exc: Exception) -> None:
    if isinstance(exc, (GraphMatchNotFoundError, AgentNotFoundError)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (GraphMatchStateError, ValueError)):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc


@router.post("/graph-match/sessions", response_model=GraphMatchResponse, status_code=status.HTTP_201_CREATED)
def start_graph_match(
    request: StartGraphMatchRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: GraphMatchService = Depends(get_graph_match_service),
) -> GraphMatchResponse:
    try:
        return _to_response(service.start(agent_id=request.agent_id, user_id=_user_id(x_user_id)))
    except Exception as exc:
        _handle_game_error(exc)


@router.post("/graph-match/sessions/{session_id}/attempts", response_model=GraphMatchResponse)
def submit_graph_attempt(
    session_id: str,
    request: SubmitGraphAttemptRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: GraphMatchService = Depends(get_graph_match_service),
) -> GraphMatchResponse:
    try:
        function = GraphFunction(
            coefficient=request.coefficient,
            base=request.base,
            horizontal_shift=request.horizontal_shift,
            vertical_shift=request.vertical_shift,
        )
        return _to_response(
            service.submit_attempt(
                session_id,
                user_id=_user_id(x_user_id),
                function=function,
                elapsed_ms=request.elapsed_ms,
            )
        )
    except Exception as exc:
        _handle_game_error(exc)


@router.post("/graph-match/sessions/{session_id}/advance", response_model=GraphMatchResponse)
def advance_graph_match(
    session_id: str,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: GraphMatchService = Depends(get_graph_match_service),
) -> GraphMatchResponse:
    try:
        return _to_response(service.advance(session_id, user_id=_user_id(x_user_id)))
    except Exception as exc:
        _handle_game_error(exc)


@router.post("/graph-match/sessions/{session_id}/quick-chats", response_model=GraphMatchResponse)
def send_graph_match_quick_chat(
    session_id: str,
    request: QuickChatRequest,
    x_user_id: str | None = Header(default=None, alias="X-User-ID"),
    service: GraphMatchService = Depends(get_graph_match_service),
) -> GraphMatchResponse:
    try:
        return _to_response(
            service.send_quick_chat(
                session_id,
                user_id=_user_id(x_user_id),
                chat=QuickChat(request.chat),
            )
        )
    except Exception as exc:
        _handle_game_error(exc)
