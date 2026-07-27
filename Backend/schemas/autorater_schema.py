from __future__ import annotations

from pydantic import BaseModel


class StartRequest(BaseModel):
    image_b64: str


class PreloadRequest(BaseModel):
    image_b64: str


class StartResponse(BaseModel):
    opener: str
    total_problems: int
    mode: str | None = None


class PreloadResponse(BaseModel):
    status: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    next_opener: str | None = None
    mode: str | None = None
    next_mode: str | None = None
    is_done: bool


class ExampleImagesResponse(BaseModel):
    images: list[str]
