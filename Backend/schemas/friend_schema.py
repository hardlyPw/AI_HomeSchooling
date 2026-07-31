from __future__ import annotations

from pydantic import BaseModel


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
