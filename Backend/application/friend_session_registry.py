from __future__ import annotations

from collections.abc import Callable
import threading

from application.services.friend_chat_service import FriendChatService


DEFAULT_FRIEND_SESSION_ID = "default"


class FriendSessionRegistry:
    """Owns one friend conversation service per client session."""

    def __init__(self, service_factory: Callable[[], FriendChatService]) -> None:
        self._service_factory = service_factory
        self._services: dict[str, FriendChatService] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str | None) -> FriendChatService:
        normalized = self._normalize_session_id(session_id)
        with self._lock:
            service = self._services.get(normalized)
            if service is None:
                service = self._service_factory()
                self._services[normalized] = service
            return service

    @staticmethod
    def _normalize_session_id(session_id: str | None) -> str:
        normalized = (session_id or "").strip()
        if not normalized:
            return DEFAULT_FRIEND_SESSION_ID
        return normalized[:128]
