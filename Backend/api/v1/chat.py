from fastapi import APIRouter, HTTPException
from schemas.chat_schema import ChatRequest, ChatResponse
from services.chat_service import ChatService

router = APIRouter()
chat_service = ChatService()

@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        reply, summary = chat_service.get_reply(
            request.message,
            request.pdf_context,
            request.figure_context,
            request.figure_image,
            request.current_video_time,
        )
        return ChatResponse(reply=reply, summary=summary)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 실패: {str(e)}")