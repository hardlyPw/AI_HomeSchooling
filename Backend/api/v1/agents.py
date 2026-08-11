from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse

from application.dependencies import get_agent_catalog_service, get_agent_chat_service
from application.services.agent_catalog_service import (
    AgentCatalogService,
    AgentNotFoundError,
    ProtectedAgentError,
)
from application.services.friend_chat_service import FriendChatService
from domain.agents.conversation import ConversationAgentDefinition
from domain.agents.conversation_creation import ConversationAgentQuestionnaire
from schemas.agent_schema import AgentListResponse, AgentSummary, CreateAgentRequest
from schemas.friend_schema import (
    FriendChatRequest,
    FriendHistory,
    FriendHistoryMessage,
    FriendState,
)


router = APIRouter()


def _to_summary(
    definition: ConversationAgentDefinition,
    service: AgentCatalogService,
) -> AgentSummary:
    return AgentSummary(
        id=definition.profile.agent_id,
        type=definition.agent_type.value,
        name=definition.profile.display_name,
        description=definition.profile.description,
        initial_affinity=definition.profile.initial_affinity,
        game_skill_tier=definition.profile.game_skill_tier.value,
        capabilities=sorted(capability.value for capability in definition.profile.capabilities),
        is_builtin=service.is_protected(definition.profile.agent_id),
    )


@router.get("", response_model=AgentListResponse)
def list_agents(
    service: AgentCatalogService = Depends(get_agent_catalog_service),
) -> AgentListResponse:
    return AgentListResponse(
        agents=[_to_summary(definition, service) for definition in service.list_agents()]
    )


@router.post("", response_model=AgentSummary, status_code=status.HTTP_201_CREATED)
def create_agent(
    request: CreateAgentRequest,
    service: AgentCatalogService = Depends(get_agent_catalog_service),
) -> AgentSummary:
    try:
        definition = service.create_agent(
            ConversationAgentQuestionnaire(**request.model_dump())
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unable to create Agent: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The Agent designer is temporarily unavailable.",
        ) from exc
    return _to_summary(definition, service)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: str,
    service: AgentCatalogService = Depends(get_agent_catalog_service),
) -> Response:
    try:
        service.delete_agent(agent_id)
    except AgentNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Agent was not found.") from exc
    except ProtectedAgentError as exc:
        raise HTTPException(status_code=409, detail="Built-in Agents cannot be deleted.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{agent_id}/state", response_model=FriendState)
def agent_state(
    service: FriendChatService = Depends(get_agent_chat_service),
) -> FriendState:
    return FriendState(affinity=service.affinity, message_count=service.message_count)


@router.get("/{agent_id}/history", response_model=FriendHistory)
def agent_history(
    service: FriendChatService = Depends(get_agent_chat_service),
) -> FriendHistory:
    return FriendHistory(
        affinity=service.affinity,
        messages=[
            FriendHistoryMessage(
                role=str(item.get("role", "")),
                text=str(item.get("text", "")),
            )
            for item in service.history
            if item.get("role") in {"user", "ai", "assistant"} and item.get("text")
        ],
    )


@router.post("/{agent_id}/reset")
def reset_agent(
    service: FriendChatService = Depends(get_agent_chat_service),
) -> dict[str, int]:
    return {"affinity": service.reset()}


@router.post("/{agent_id}/debug/cooldown")
def debug_agent_cooldown(
    service: FriendChatService = Depends(get_agent_chat_service),
) -> dict[str, bool]:
    service.force_next_cooldown()
    return {"ok": True}


@router.post("/{agent_id}/debug/double-text")
def debug_agent_double_text(
    service: FriendChatService = Depends(get_agent_chat_service),
) -> dict[str, bool]:
    service.force_next_double_text()
    return {"ok": True}


@router.post("/{agent_id}/debug/cooldown-end")
def debug_agent_cooldown_end(
    service: FriendChatService = Depends(get_agent_chat_service),
) -> dict[str, bool]:
    service.end_cooldown()
    return {"ok": True}


@router.post("/{agent_id}/chat/stream")
def stream_agent_chat(
    request: FriendChatRequest,
    service: FriendChatService = Depends(get_agent_chat_service),
) -> StreamingResponse:
    def event_generator():
        try:
            for event in service.stream_reply(request.message):
                yield f"data: {json.dumps(event.to_payload(), ensure_ascii=False)}\n\n"
        except Exception as exc:
            error = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {error}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
