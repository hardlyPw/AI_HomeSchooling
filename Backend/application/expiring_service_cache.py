from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import threading
import time
from typing import Generic, TypeVar


KeyT = TypeVar("KeyT")
ValueT = TypeVar("ValueT")


@dataclass
class _CacheEntry(Generic[ValueT]):
    value: ValueT
    last_access: float


class ExpiringServiceCache(Generic[KeyT, ValueT]):
    """Thread-safe bounded cache for session-owned application services."""

    def __init__(
        self,
        *,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._clock = clock
        self._entries: dict[KeyT, _CacheEntry[ValueT]] = {}
        self._lock = threading.RLock()

    def get_or_create(self, key: KeyT, factory: Callable[[], ValueT]) -> ValueT:
        with self._lock:
            now = self._clock()
            self._evict_expired(now)
            entry = self._entries.get(key)
            if entry is not None:
                entry.last_access = now
                return entry.value

            if len(self._entries) >= self._max_entries:
                oldest_key = min(
                    self._entries,
                    key=lambda candidate: self._entries[candidate].last_access,
                )
                self._entries.pop(oldest_key)

            value = factory()
            self._entries[key] = _CacheEntry(value=value, last_access=now)
            return value

    @property
    def size(self) -> int:
        with self._lock:
            self._evict_expired(self._clock())
            return len(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def _evict_expired(self, now: float) -> None:
        expired = [
            key
            for key, entry in self._entries.items()
            if now - entry.last_access >= self._ttl_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)
