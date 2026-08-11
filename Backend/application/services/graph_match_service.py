from __future__ import annotations

from datetime import datetime, timezone
import threading

from application.services.agent_catalog_service import AgentCatalogService, AgentNotFoundError
from domain.games.graph_match import (
    GameAttempt,
    GraphFunction,
    GraphMatchSession,
    MAX_ATTEMPTS,
    QUICK_CHAT_TEXT,
    QuickChat,
    QuickChatEvent,
    create_agent_guess,
    graph_similarity,
)
from domain.games.repository import GameActivityMemory, GraphMatchRepository


class GraphMatchNotFoundError(LookupError):
    pass


class GraphMatchStateError(ValueError):
    pass


class GraphMatchService:
    def __init__(
        self,
        repository: GraphMatchRepository,
        agent_catalog: AgentCatalogService,
        activity_memory: GameActivityMemory,
    ) -> None:
        self._repository = repository
        self._agent_catalog = agent_catalog
        self._activity_memory = activity_memory
        self._lock = threading.RLock()

    def start(self, *, agent_id: str, user_id: str) -> GraphMatchSession:
        definition = self._agent_catalog.get_agent(agent_id)
        session = GraphMatchSession.create(
            user_id=user_id,
            agent_id=agent_id,
            agent_name=definition.profile.display_name,
            agent_skill=definition.profile.game_skill_tier,
        )
        self._repository.save(session)
        return session

    def get(self, session_id: str, *, user_id: str) -> GraphMatchSession:
        session = self._repository.get(session_id)
        if session is None or session.user_id != user_id:
            raise GraphMatchNotFoundError("Graph Match session was not found")
        return session

    def submit_attempt(
        self,
        session_id: str,
        *,
        user_id: str,
        function: GraphFunction,
        elapsed_ms: int,
    ) -> GraphMatchSession:
        with self._lock:
            session = self.get(session_id, user_id=user_id)
            if session.completed:
                raise GraphMatchStateError("This game is already complete")
            round_state = session.current_round
            if round_state.completed:
                raise GraphMatchStateError("Advance to the next round first")
            if len(round_state.attempts) >= MAX_ATTEMPTS:
                raise GraphMatchStateError("No attempts remain in this round")

            score = graph_similarity(round_state.target, function)
            round_state.attempts.append(
                GameAttempt(function=function, score=score, elapsed_ms=max(0, elapsed_ms))
            )
            if score >= 99.9 or len(round_state.attempts) == MAX_ATTEMPTS or elapsed_ms >= 60_000:
                self._complete_round(session)
            self._repository.save(session)
            return session

    def advance(self, session_id: str, *, user_id: str) -> GraphMatchSession:
        with self._lock:
            session = self.get(session_id, user_id=user_id)
            if session.completed:
                return session
            if not session.current_round.completed:
                raise GraphMatchStateError("Finish the current round before advancing")
            session.current_round_index += 1
            self._repository.save(session)
            return session

    def send_quick_chat(
        self,
        session_id: str,
        *,
        user_id: str,
        chat: QuickChat,
    ) -> GraphMatchSession:
        with self._lock:
            session = self.get(session_id, user_id=user_id)
            session.quick_chats.append(
                QuickChatEvent(
                    sender="user",
                    chat=chat,
                    text=QUICK_CHAT_TEXT[chat],
                    created_at=datetime.now(timezone.utc),
                )
            )
            self._repository.save(session)
            return session

    def _complete_round(self, session: GraphMatchSession) -> None:
        round_state = session.current_round
        agent_guess = create_agent_guess(
            round_state.target,
            session.agent_skill,
            seed=f"{session.id}:{round_state.number}",
        )
        round_state.agent_guess = agent_guess
        round_state.agent_score = graph_similarity(round_state.target, agent_guess)
        user_score = round_state.best_attempt.score if round_state.best_attempt else 0.0
        if user_score > round_state.agent_score:
            round_state.winner = "user"
            agent_chat = QuickChat.NICE
        elif user_score < round_state.agent_score:
            round_state.winner = "agent"
            agent_chat = QuickChat.TRY_HARDER
        else:
            round_state.winner = "draw"
            agent_chat = QuickChat.CLOSE
        round_state.completed = True
        session.quick_chats.append(
            QuickChatEvent(
                sender="agent",
                chat=agent_chat,
                text=QUICK_CHAT_TEXT[agent_chat],
                created_at=datetime.now(timezone.utc),
            )
        )

        if session.current_round_index == len(session.rounds) - 1:
            session.completed = True
            session.completed_at = datetime.now(timezone.utc)
            self._activity_memory.record(session)
