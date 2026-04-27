from pydantic import BaseModel

# 클라이언트로부터 받을 데이터 형식
class ChatRequest(BaseModel):
    message: str

# 클라이언트로 보낼 데이터 형식
class ChatResponse(BaseModel):
    reply: str
    status: str = "success"