import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from application.dependencies import get_friend_chat_service
from application.services.friend_chat_service import FriendChatService
from schemas.friend_schema import (
    FriendChatRequest,
    FriendHistory,
    FriendHistoryMessage,
    FriendState,
)


router = APIRouter()


@router.get("/state", response_model=FriendState)
def state(service: FriendChatService = Depends(get_friend_chat_service)):
    return FriendState(
        affinity=service.affinity,
        message_count=service.message_count,
    )


@router.get("/history", response_model=FriendHistory)
def history(service: FriendChatService = Depends(get_friend_chat_service)):
    return FriendHistory(
        affinity=service.affinity,
        messages=[
            FriendHistoryMessage(role=str(item.get("role", "")), text=str(item.get("text", "")))
            for item in service.history
            if item.get("role") in {"user", "ai", "assistant"} and item.get("text")
        ],
    )


@router.post("/reset")
def reset(service: FriendChatService = Depends(get_friend_chat_service)):
    return {"affinity": service.reset()}


@router.post("/debug/cooldown")
def debug_cooldown(service: FriendChatService = Depends(get_friend_chat_service)):
    service.force_next_cooldown()
    return {"ok": True}


@router.post("/debug/double-text")
def debug_double_text(service: FriendChatService = Depends(get_friend_chat_service)):
    service.force_next_double_text()
    return {"ok": True}


@router.post("/debug/cooldown-end")
def debug_cooldown_end(service: FriendChatService = Depends(get_friend_chat_service)):
    service.end_cooldown()
    return {"ok": True}


@router.post("/chat/stream")
def chat_stream(
    request: FriendChatRequest,
    service: FriendChatService = Depends(get_friend_chat_service),
):
    def event_generator():
        try:
            for event in service.stream_reply(request.message):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            err = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
