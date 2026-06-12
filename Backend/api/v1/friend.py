import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.friend_service import FriendService

router = APIRouter()
friend_service = FriendService()


class FriendChatRequest(BaseModel):
    message: str


class FriendState(BaseModel):
    affinity: int
    message_count: int


class FriendHistoryMessage(BaseModel):
    role: str
    text: str


class FriendHistory(BaseModel):
    affinity: int
    messages: list[FriendHistoryMessage]


@router.get("/state", response_model=FriendState)
def state():
    return FriendState(
        affinity=friend_service.affinity,
        message_count=len(friend_service.history) // 2,
    )


@router.get("/history", response_model=FriendHistory)
def history():
    return FriendHistory(
        affinity=friend_service.affinity,
        messages=[
            FriendHistoryMessage(role=str(item.get("role", "")), text=str(item.get("text", "")))
            for item in friend_service.history
            if item.get("role") in {"user", "ai", "assistant"} and item.get("text")
        ],
    )


@router.post("/reset")
def reset():
    friend_service.reset()
    return {"affinity": friend_service.affinity}


@router.post("/debug/cooldown")
def debug_cooldown():
    friend_service.force_next_cooldown()
    return {"ok": True}


@router.post("/debug/double-text")
def debug_double_text():
    friend_service.force_next_double_text()
    return {"ok": True}


@router.post("/chat/stream")
def chat_stream(request: FriendChatRequest):
    def event_generator():
        try:
            for event in friend_service.stream_reply(request.message):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            err = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
