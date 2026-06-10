from pydantic import BaseModel

class ChatRequest(BaseModel):
    message: str
    pdf_context: str | None = None
    figure_context: str | None = None
    figure_images: list[str] | None = None
    current_video_time: float | None = None

class ChatResponse(BaseModel):
    reply: str
    summary: str
    status: str = "success"

class SummarizeRequest(BaseModel):
    text: str

class SummarizeResponse(BaseModel):
    summary: str