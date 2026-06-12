import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from schemas.chat_schema import ChatRequest
from services.chat_service import ChatService

router = APIRouter()
chat_service = ChatService()


@router.post("/chat/stream")
def chat_stream(request: ChatRequest):
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