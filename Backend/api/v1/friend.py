"""Jiho 친구 Agent 채팅 API.

main.py에서 prefix="/api/v1/friend"로 등록되므로 실제 경로는
GET/POST /api/v1/friend/... 형태가 된다.

호출 주체:
- frontend/src/FriendView.tsx에서만 직접 호출한다.
- 일반 수업 Teacher 채팅(App.tsx sendMessage)이나 Isabella Autorater와는 별도 API다.
- 현재 Jiho 채팅은 message 텍스트만 받고, PDF/이미지 컨텍스트는 받지 않는다.
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.friend_service import FriendService

router = APIRouter()
friend_service = FriendService()


class FriendChatRequest(BaseModel):
    """Jiho 채팅 요청 body. 현재는 텍스트 메시지만 받는다."""

    message: str


class FriendState(BaseModel):
    """프론트가 Jiho의 간단한 현재 상태만 확인할 때 쓰는 응답 형태."""

    affinity: int
    message_count: int


class FriendHistoryMessage(BaseModel):
    """히스토리 복원용 개별 메시지 형태."""

    role: str
    text: str


class FriendHistory(BaseModel):
    """FriendView 첫 진입 시 기존 대화와 호감도를 복원하기 위한 응답 형태."""

    affinity: int
    messages: list[FriendHistoryMessage]


@router.get("/state", response_model=FriendState)
def state():
    """GET /api/v1/friend/state

    Jiho의 현재 호감도와 대화 턴 수만 가볍게 확인하는 API.
    현재 FriendView 핵심 흐름에서는 history를 더 많이 쓰지만, 상태만 따로 볼 때 사용할 수 있다.
    """
    return FriendState(
        affinity=friend_service.affinity,
        message_count=len(friend_service.history) // 2,
    )


@router.get("/history", response_model=FriendHistory)
def history():
    """GET /api/v1/friend/history

    FriendView가 처음 렌더링될 때 호출된다.
    서버 메모리에 남아 있는 Jiho 대화 기록과 현재 호감도를 가져와 화면에 복원한다.
    """
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
    """POST /api/v1/friend/reset

    FriendView의 디버그 reset 버튼에서 호출된다.
    단기 대화 기록, 호감도, cooldown/double-text 플래그를 초기화한다.
    """
    friend_service.reset()
    return {"affinity": friend_service.affinity}


@router.post("/debug/cooldown")
def debug_cooldown():
    """POST /api/v1/friend/debug/cooldown

    FriendView 디버그 패널의 cooldown 버튼에서 호출된다.
    다음 사용자 메시지에서 Jiho가 강제로 자리를 비운 것처럼 동작하게 예약한다.
    """
    friend_service.force_next_cooldown()
    return {"ok": True}


@router.post("/debug/double-text")
def debug_double_text():
    """POST /api/v1/friend/debug/double-text

    FriendView 디버그 패널의 double 버튼에서 호출된다.
    다음 사용자 메시지에서 Jiho가 답장을 두 말풍선으로 나눠 보내게 예약한다.
    """
    friend_service.force_next_double_text()
    return {"ok": True}


@router.post("/debug/cooldown-end")
def debug_cooldown_end():
    """POST /api/v1/friend/debug/cooldown-end

    FriendView 디버그 패널의 cooldown_end 버튼에서 호출된다.
    cooldown 대기 중인 Jiho를 즉시 깨워서 답변 흐름을 계속 진행하게 한다.
    """
    friend_service.end_cooldown()
    return {"ok": True}


@router.post("/chat/stream")
def chat_stream(request: FriendChatRequest):
    """POST /api/v1/friend/chat/stream

    FriendView에서 사용자가 Jiho에게 메시지를 보낼 때마다 호출된다.
    FriendService.stream_reply()가 만드는 이벤트를 SSE로 그대로 흘려보낸다.

    주요 이벤트:
    - {"status": "delayed"|"cooldown"}: 프론트가 typing/offline 상태를 바꿈
    - {"decision": {...}}: 디버그 패널에 감정, 타이밍, 호감도 변화 표시
    - {"delta": "..."}: 실제 Jiho 답변 조각
    - {"message_break": true}: double-text일 때 말풍선을 나눔
    - {"affinity": 70, ...}: 호감도 UI 갱신
    - {"done": true}: 한 턴 종료
    """
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
