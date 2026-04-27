from fastapi import APIRouter
from schemas.chat_schema import ChatRequest, ChatResponse
from services.chat_service import ChatService

router = APIRouter()
chat_service = ChatService()

@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # 서비스 레이어 호출
    mock_reply = await chat_service.get_mock_response(request.message)
    
    return ChatResponse(reply=mock_reply)