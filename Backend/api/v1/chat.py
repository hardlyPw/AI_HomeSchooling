"""일반 수업 Teacher 채팅 API.

main.py에서 prefix="/api/v1"로 등록되므로 실제 경로는
POST /api/v1/chat/stream 이다.

호출 시점:
- frontend/src/App.tsx의 일반 학습 채팅 sendMessage()에서 호출된다.
- Isabella/Autorater 모드가 아닐 때만 이 API를 탄다.
- 사용자가 채팅 입력을 보내거나, PDF/이미지 선택 후 "Explain this." 흐름으로 보낼 때 호출된다.
"""

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from schemas.chat_schema import ChatRequest
from services.chat_service import ChatService

router = APIRouter()
chat_service = ChatService()


@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
    """Teacher 답변을 SSE(text/event-stream)로 토큰 단위 스트리밍한다.

    request에는 message 외에도 PDF 선택문, figure 설명/이미지, 현재 영상 시간이 들어올 수 있다.
    ChatService가 이 컨텍스트를 합쳐 AI_Teacher로 넘기고, 여기서는 프론트가 읽기 좋은
    {"delta": "..."} 이벤트로 감싸서 보낸다.
    """
    def event_generator():
        try:
            for delta in chat_service.get_reply_stream(
                request.message,
                request.pdf_context,
                request.figure_context,
                request.figure_images,
                request.current_video_time,
            ):
                payload = json.dumps({"delta": delta}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            yield "data: {\"done\": true}\n\n"
        except Exception as exc:
            err = json.dumps({"error": str(exc)}, ensure_ascii=False)
            yield f"data: {err}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
