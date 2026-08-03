from __future__ import annotations

from dataclasses import dataclass
import re
import threading


@dataclass(frozen=True)
class ConversationMemoryNamespace:
    user_id: str
    agent_id: str


class NamespacedConversationMemoryStore:
    """Process-local long-term memory isolated by user and Agent."""

    def __init__(self, max_entries_per_namespace: int = 100) -> None:
        self._max_entries = max_entries_per_namespace
        self._entries: dict[ConversationMemoryNamespace, list[str]] = {}
        self._lock = threading.RLock()

    def search(
        self,
        namespace: ConversationMemoryNamespace,
        query_text: str,
        top_k: int,
    ) -> list[dict]:
        query_terms = self._terms(query_text)
        with self._lock:
            entries = list(self._entries.get(namespace, ()))

        scored: list[tuple[float, str]] = []
        for index, description in enumerate(entries):
            overlap = len(query_terms & self._terms(description))
            recency = (index + 1) / max(1, len(entries))
            score = overlap * 2.0 + recency * 0.25
            if overlap > 0:
                scored.append((score, description))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [
            {"description": description, "score": round(score, 3)}
            for score, description in scored[:top_k]
        ]

    def record_turn(
        self,
        namespace: ConversationMemoryNamespace,
        user_message: str,
        agent_reply: str,
    ) -> None:
        description = f"User said: {user_message.strip()} Agent replied: {agent_reply.strip()}"
        with self._lock:
            entries = self._entries.setdefault(namespace, [])
            entries.append(description)
            del entries[:-self._max_entries]

    def clear(self, namespace: ConversationMemoryNamespace) -> None:
        with self._lock:
            self._entries.pop(namespace, None)

    def entries_for(self, namespace: ConversationMemoryNamespace) -> list[str]:
        with self._lock:
            return list(self._entries.get(namespace, ()))

    @staticmethod
    def _terms(text: str) -> set[str]:
        return set(re.findall(r"[a-z0-9가-힣]+", text.lower()))
