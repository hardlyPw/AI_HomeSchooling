from __future__ import annotations

from datetime import datetime, timezone
import random
import threading

from application.services.agent_catalog_service import AgentCatalogService
from application.services.leaderboard_service import LeaderboardService
from domain.games.leaderboard import GameId
from domain.games.memory_match import AgentCardTurn, MemoryMatchSession
from domain.games.repository import MemoryMatchRepository


class MemoryMatchNotFoundError(LookupError):
    pass


class MemoryMatchStateError(ValueError):
    pass


class MemoryMatchService:
    def __init__(
        self,
        repository: MemoryMatchRepository,
        agent_catalog: AgentCatalogService,
        leaderboard: LeaderboardService,
    ) -> None:
        self._repository = repository
        self._agent_catalog = agent_catalog
        self._leaderboard = leaderboard
        self._lock = threading.RLock()

    def start(self, *, user_id: str, agent_id: str, player_name: str = "You") -> MemoryMatchSession:
        definition = self._agent_catalog.get_agent(agent_id)
        session = MemoryMatchSession.create(
            user_id=user_id,
            player_name=player_name,
            agent_id=agent_id,
            agent_name=definition.profile.display_name,
            agent_skill=definition.profile.game_skill_tier,
        )
        self._repository.save(session)
        return session

    def get(self, session_id: str, *, user_id: str) -> MemoryMatchSession:
        session = self._repository.get(session_id)
        if session is None or session.user_id != user_id:
            raise MemoryMatchNotFoundError("Memory Match session was not found")
        return session

    def ready(self, session_id: str, *, user_id: str) -> MemoryMatchSession:
        with self._lock:
            session = self.get(session_id, user_id=user_id)
            if session.phase == "preview":
                session.phase = "player_turn"
                session.last_agent_turns = ()
                self._repository.save(session)
            return session

    def play(self, session_id: str, *, user_id: str, indices: tuple[int, int]) -> MemoryMatchSession:
        with self._lock:
            session = self.get(session_id, user_id=user_id)
            if session.phase != "player_turn" or session.completed:
                raise MemoryMatchStateError("It is not the player's turn")
            first, second = indices
            if first == second or any(index < 0 or index >= len(session.board) for index in indices):
                raise MemoryMatchStateError("Choose two different cards")
            if first in session.matched_indices or second in session.matched_indices:
                raise MemoryMatchStateError("A matched card cannot be selected again")
            session.agent_seen[first] = session.board[first]
            session.agent_seen[second] = session.board[second]
            if session.board[first] == session.board[second]:
                session.matched_indices.update(indices)
                session.user_score += 1
                session.last_agent_turns = ()
            else:
                session.phase = "agent_turn"
                session.last_agent_turns = self._run_agent_turn(session)
                if not session.completed:
                    session.phase = "player_turn"
            self._finish_if_complete(session)
            self._repository.save(session)
            return session

    def pass_turn(self, session_id: str, *, user_id: str) -> MemoryMatchSession:
        with self._lock:
            session = self.get(session_id, user_id=user_id)
            if session.phase != "player_turn" or session.completed:
                raise MemoryMatchStateError("It is not the player's turn")
            session.phase = "agent_turn"
            session.last_agent_turns = self._run_agent_turn(session)
            if not session.completed:
                session.phase = "player_turn"
            self._finish_if_complete(session)
            self._repository.save(session)
            return session

    def _run_agent_turn(self, session: MemoryMatchSession) -> tuple[AgentCardTurn, ...]:
        rng = random.Random(f"{session.id}:{session.user_score}:{session.agent_score}:{len(session.matched_indices)}")
        turns: list[AgentCardTurn] = []
        while not session.completed:
            available = [index for index in range(len(session.board)) if index not in session.matched_indices]
            known_pairs: list[tuple[int, int]] = []
            by_value: dict[int, list[int]] = {}
            for index, value in session.agent_seen.items():
                if index in available:
                    by_value.setdefault(value, []).append(index)
            for indices in by_value.values():
                if len(indices) >= 2:
                    known_pairs.append((indices[0], indices[1]))
            if known_pairs:
                indices = rng.choice(known_pairs)
            else:
                indices = tuple(rng.sample(available, k=2))
            values = (session.board[indices[0]], session.board[indices[1]])
            session.agent_seen[indices[0]] = values[0]
            session.agent_seen[indices[1]] = values[1]
            matched = values[0] == values[1]
            if matched:
                session.matched_indices.update(indices)
                session.agent_score += 1
            turns.append(AgentCardTurn(indices, values, matched, session.agent_score))
            if not matched:
                break
        return tuple(turns)

    def _finish_if_complete(self, session: MemoryMatchSession) -> None:
        if not session.completed or session.completed_at is not None:
            return
        session.phase = "completed"
        session.completed_at = datetime.now(timezone.utc)
        outcome = "Won" if session.user_score > session.agent_score else "Lost" if session.user_score < session.agent_score else "Drew"
        self._leaderboard.record(
            game_id=GameId.MEMORY_MATCH,
            user_id=session.user_id,
            player_name=session.player_name,
            score=session.user_score,
            detail=f"{outcome} {session.user_score}-{session.agent_score} vs {session.agent_name}",
        )
