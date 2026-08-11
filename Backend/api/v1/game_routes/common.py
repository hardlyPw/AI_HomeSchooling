from __future__ import annotations

from fastapi import HTTPException

from application.services.agent_catalog_service import AgentNotFoundError
from application.services.graph_challenge_service import (
    GraphChallengeNotFoundError,
    GraphChallengeStateError,
)
from application.services.memory_match_service import (
    MemoryMatchNotFoundError,
    MemoryMatchStateError,
)


def user_id(value: str | None) -> str:
    return (value or "demo-user").strip() or "demo-user"


def handle_game_error(exc: Exception) -> None:
    if isinstance(
        exc,
        (GraphChallengeNotFoundError, MemoryMatchNotFoundError, AgentNotFoundError),
    ):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (GraphChallengeStateError, MemoryMatchStateError, ValueError)):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    raise exc
