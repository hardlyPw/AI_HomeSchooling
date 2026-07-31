import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from application.dependencies import get_lesson_chat_service
from application.services.lesson_chat_service import LessonChatService
from domain.chat.messages import LessonChatInput
from schemas.chat_schema import ChatRequest


router = APIRouter()


@router.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    service: LessonChatService = Depends(get_lesson_chat_service),
):
    def event_generator():
        try:
            lesson_input = LessonChatInput(
                message=request.message,
                pdf_context=request.pdf_context,
                figure_context=request.figure_context,
                figure_images=request.figure_images,
                current_video_time=request.current_video_time,
            )
            for delta in service.get_reply_stream(lesson_input):
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
