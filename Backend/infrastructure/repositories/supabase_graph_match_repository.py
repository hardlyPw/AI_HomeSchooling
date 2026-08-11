from __future__ import annotations

from datetime import datetime
import threading

from domain.agents.conversation import GameSkillTier
from domain.games.graph_match import (
    GameAttempt,
    GraphFunction,
    GraphMatchRound,
    GraphMatchSession,
    QuickChat,
    QuickChatEvent,
)


class SupabaseGraphMatchRepository:
    """Stores active sessions locally and persists every state change to Supabase."""

    def __init__(self, supabase_client) -> None:
        self._client = supabase_client
        self._active: dict[str, GraphMatchSession] = {}
        self._lock = threading.RLock()

    def save(self, session: GraphMatchSession) -> None:
        with self._lock:
            self._client.table("graph_match_sessions").upsert(
                self._session_row(session),
                on_conflict="id",
            ).execute()
            self._client.table("graph_match_rounds").upsert(
                [self._round_row(session.id, item) for item in session.rounds],
                on_conflict="session_id,round_number",
            ).execute()
            if session.quick_chats:
                self._client.table("graph_match_quick_chats").upsert(
                    [self._quick_chat_row(session.id, item) for item in session.quick_chats],
                    on_conflict="id",
                ).execute()
            self._active[session.id] = session

    def get(self, session_id: str) -> GraphMatchSession | None:
        with self._lock:
            active = self._active.get(session_id)
            if active is not None:
                return active

            response = (
                self._client.table("graph_match_sessions")
                .select("*")
                .eq("id", session_id)
                .limit(1)
                .execute()
            )
            rows = response.data if isinstance(response.data, list) else []
            if not rows:
                return None
            session = self._restore_session(rows[0])
            self._active[session.id] = session
            return session

    def _restore_session(self, row: dict) -> GraphMatchSession:
        rounds_response = (
            self._client.table("graph_match_rounds")
            .select("*")
            .eq("session_id", row["id"])
            .order("round_number")
            .execute()
        )
        chat_response = (
            self._client.table("graph_match_quick_chats")
            .select("*")
            .eq("session_id", row["id"])
            .order("created_at")
            .execute()
        )
        rounds = [self._restore_round(item) for item in rounds_response.data or []]
        chats = [
            QuickChatEvent(
                id=item["id"],
                sender=item["sender"],
                chat=QuickChat(item["chat"]),
                text=item["text"],
                created_at=self._datetime(item["created_at"]),
            )
            for item in chat_response.data or []
        ]
        return GraphMatchSession(
            id=row["id"],
            user_id=row["user_id"],
            agent_id=row["agent_id"],
            agent_name=row["agent_name"],
            agent_skill=GameSkillTier(row["agent_skill"]),
            rounds=rounds,
            current_round_index=int(row["current_round_index"]),
            quick_chats=chats,
            completed=bool(row["completed"]),
            created_at=self._datetime(row["created_at"]),
            completed_at=self._datetime(row["completed_at"]) if row.get("completed_at") else None,
            activity_memories=tuple(row.get("activity_memories") or ()),
        )

    @staticmethod
    def _restore_round(row: dict) -> GraphMatchRound:
        target = SupabaseGraphMatchRepository._function_from(row, "target")
        attempts = []
        if row.get("user_coefficient") is not None:
            attempts.append(
                GameAttempt(
                    function=SupabaseGraphMatchRepository._function_from(row, "user"),
                    graph_score=float(row["user_graph_score"]),
                    time_bonus=float(row["user_time_bonus"]),
                    score=float(row["user_score"]),
                    elapsed_ms=int(row["user_elapsed_ms"]),
                )
            )
        agent_guess = None
        if row.get("agent_coefficient") is not None:
            agent_guess = SupabaseGraphMatchRepository._function_from(row, "agent")
        return GraphMatchRound(
            number=int(row["round_number"]),
            target=target,
            attempts=attempts,
            agent_guess=agent_guess,
            agent_graph_score=SupabaseGraphMatchRepository._optional_float(row.get("agent_graph_score")),
            agent_time_bonus=SupabaseGraphMatchRepository._optional_float(row.get("agent_time_bonus")),
            agent_score=SupabaseGraphMatchRepository._optional_float(row.get("agent_score")),
            agent_elapsed_ms=int(row["agent_elapsed_ms"]) if row.get("agent_elapsed_ms") is not None else None,
            winner=row.get("winner"),
            completed=bool(row["completed"]),
        )

    @staticmethod
    def _session_row(session: GraphMatchSession) -> dict:
        return {
            "id": session.id,
            "user_id": session.user_id,
            "agent_id": session.agent_id,
            "agent_name": session.agent_name,
            "agent_skill": session.agent_skill.value,
            "current_round_index": session.current_round_index,
            "user_total_score": session.user_total_score,
            "agent_total_score": session.agent_total_score,
            "user_round_wins": session.user_round_wins,
            "agent_round_wins": session.agent_round_wins,
            "completed": session.completed,
            "created_at": session.created_at.isoformat(),
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            "activity_memories": list(session.activity_memories),
        }

    @staticmethod
    def _round_row(session_id: str, round_state: GraphMatchRound) -> dict:
        row = {
            "session_id": session_id,
            "round_number": round_state.number,
            **SupabaseGraphMatchRepository._function_row("target", round_state.target),
            "completed": round_state.completed,
            "winner": round_state.winner,
            "user_coefficient": None,
            "user_base": None,
            "user_horizontal_shift": None,
            "user_vertical_shift": None,
            "user_graph_score": None,
            "user_time_bonus": None,
            "user_score": None,
            "user_elapsed_ms": None,
            "agent_coefficient": None,
            "agent_base": None,
            "agent_horizontal_shift": None,
            "agent_vertical_shift": None,
            "agent_graph_score": round_state.agent_graph_score,
            "agent_time_bonus": round_state.agent_time_bonus,
            "agent_score": round_state.agent_score,
            "agent_elapsed_ms": round_state.agent_elapsed_ms,
        }
        if round_state.best_attempt:
            attempt = round_state.best_attempt
            row.update(SupabaseGraphMatchRepository._function_row("user", attempt.function))
            row.update(
                user_graph_score=attempt.graph_score,
                user_time_bonus=attempt.time_bonus,
                user_score=attempt.score,
                user_elapsed_ms=attempt.elapsed_ms,
            )
        if round_state.agent_guess:
            row.update(SupabaseGraphMatchRepository._function_row("agent", round_state.agent_guess))
        return row

    @staticmethod
    def _quick_chat_row(session_id: str, event: QuickChatEvent) -> dict:
        return {
            "id": event.id,
            "session_id": session_id,
            "sender": event.sender,
            "chat": event.chat.value,
            "text": event.text,
            "created_at": event.created_at.isoformat(),
        }

    @staticmethod
    def _function_row(prefix: str, function: GraphFunction) -> dict:
        return {
            f"{prefix}_coefficient": function.coefficient,
            f"{prefix}_base": function.base,
            f"{prefix}_horizontal_shift": function.horizontal_shift,
            f"{prefix}_vertical_shift": function.vertical_shift,
        }

    @staticmethod
    def _function_from(row: dict, prefix: str) -> GraphFunction:
        return GraphFunction(
            coefficient=int(row[f"{prefix}_coefficient"]),
            base=float(row[f"{prefix}_base"]),
            horizontal_shift=int(row[f"{prefix}_horizontal_shift"]),
            vertical_shift=int(row[f"{prefix}_vertical_shift"]),
        )

    @staticmethod
    def _optional_float(value) -> float | None:
        return float(value) if value is not None else None

    @staticmethod
    def _datetime(value: str) -> datetime:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
