from __future__ import annotations

from domain.games.graph_match import GraphMatchSession
from infrastructure.storage.namespaced_conversation_memory import (
    ConversationMemoryNamespace,
    NamespacedConversationMemoryStore,
)


class GameActivityMemoryWriter:
    """Projects notable game outcomes into Agent long-term memory."""

    def __init__(self, memory_store: NamespacedConversationMemoryStore) -> None:
        self._memory_store = memory_store

    def record(self, session: GraphMatchSession) -> tuple[str, ...]:
        memories = self._build_memories(session)
        for description in memories:
            if session.agent_id == "jiho":
                self._record_jiho_memory(description)
            else:
                self._memory_store.record_activity(
                    ConversationMemoryNamespace(session.user_id, session.agent_id),
                    description,
                )
        return memories

    @staticmethod
    def _build_memories(session: GraphMatchSession) -> tuple[str, ...]:
        best_scores = [
            round(best.score, 1)
            for round_state in session.rounds
            if (best := round_state.best_attempt) is not None
        ]
        if not best_scores:
            return ()

        memories: list[str] = []
        if session.user_round_wins >= 2:
            memories.append(
                f"The user beat {session.agent_name} {session.user_round_wins}-{session.agent_round_wins} "
                "in a three-round Graph Match game about exponential functions."
            )
        elif session.agent_round_wins >= 2:
            memories.append(
                f"The user played a full Graph Match game with {session.agent_name}; "
                f"{session.agent_name} won {session.agent_round_wins}-{session.user_round_wins}."
            )

        if max(best_scores) >= 99.9:
            memories.append(
                "The user exactly matched an exponential-function graph during Graph Match."
            )
        elif sum(best_scores) / len(best_scores) < 40:
            memories.append(
                "The user struggled to match the exponential-function graphs in Graph Match, "
                "so transformations may be worth practicing together."
            )
        return tuple(memories[:2])

    @staticmethod
    def _record_jiho_memory(description: str) -> None:
        try:
            from Agent.AI_Friend import record_activity_memory

            record_activity_memory(description, poignancy=4)
        except Exception:
            # A game result must still complete when optional Supabase memory is offline.
            return
