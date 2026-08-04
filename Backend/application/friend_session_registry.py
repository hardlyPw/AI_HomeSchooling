from __future__ import annotations

from collections.abc import Callable

from application.expiring_service_cache import ExpiringServiceCache
from application.services.friend_chat_service import FriendChatService


DEFAULT_FRIEND_SESSION_ID = "default"


class FriendSessionRegistry:
    """Owns one friend conversation service per client session."""

    def __init__(
        self,
        service_factory: Callable[[], FriendChatService],
        *,
        ttl_seconds: float = 3600,
        max_sessions: int = 256,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._service_factory = service_factory
        cache_options = {
            "ttl_seconds": ttl_seconds,
            "max_entries": max_sessions,
        }
        if clock is not None:
            cache_options["clock"] = clock
        self._services = ExpiringServiceCache[str, FriendChatService](**cache_options)

    def get(self, session_id: str | None) -> FriendChatService:
        normalized = self._normalize_session_id(session_id)
        return self._services.get_or_create(normalized, self._service_factory)

    @property
    def session_count(self) -> int:
        return self._services.size

    @staticmethod
    def _normalize_session_id(session_id: str | None) -> str:
        normalized = (session_id or "").strip()
        if not normalized:
            return DEFAULT_FRIEND_SESSION_ID
        return normalized[:128]
