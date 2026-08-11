from __future__ import annotations

from datetime import datetime, timezone
import threading

from application.services.leaderboard_service import LeaderboardService
from domain.games.graph_challenge import (
    GraphChallengeAttempt,
    GraphChallengeSession,
    graph_similarity,
    time_bonus,
)
from domain.games.leaderboard import GameId
from domain.games.math_expression import MathExpression
from domain.games.repository import GraphChallengeRepository


class GraphChallengeNotFoundError(LookupError):
    pass


class GraphChallengeStateError(ValueError):
    pass


class GraphChallengeService:
    def __init__(self, repository: GraphChallengeRepository, leaderboard: LeaderboardService) -> None:
        self._repository = repository
        self._leaderboard = leaderboard
        self._lock = threading.RLock()

    def start(self, *, user_id: str, player_name: str = "You") -> GraphChallengeSession:
        session = GraphChallengeSession.create(user_id=user_id, player_name=player_name)
        self._repository.save(session)
        return session

    def get(self, session_id: str, *, user_id: str) -> GraphChallengeSession:
        session = self._repository.get(session_id)
        if session is None or session.user_id != user_id:
            raise GraphChallengeNotFoundError("Graph Challenge session was not found")
        return session

    def submit(self, session_id: str, *, user_id: str, expression: str, elapsed_ms: int) -> GraphChallengeSession:
        with self._lock:
            session = self.get(session_id, user_id=user_id)
            if session.completed:
                raise GraphChallengeStateError("This challenge is already complete")
            round_state = session.current_round
            if round_state.completed:
                raise GraphChallengeStateError("Advance to the next round first")
            guess = MathExpression(expression)
            graph_score = graph_similarity(round_state.target.expression, guess)
            bonus = time_bonus(elapsed_ms)
            round_state.attempt = GraphChallengeAttempt(
                expression=expression.strip(),
                graph_score=graph_score,
                time_bonus=bonus,
                score=round(graph_score + bonus, 1),
                elapsed_ms=max(0, elapsed_ms),
            )
            if session.current_round_index == len(session.rounds) - 1:
                session.completed = True
                session.completed_at = datetime.now(timezone.utc)
                self._leaderboard.record(
                    game_id=GameId.GRAPH_CHALLENGE,
                    user_id=session.user_id,
                    player_name=session.player_name,
                    score=session.total_score,
                    detail="3 rounds",
                )
            self._repository.save(session)
            return session

    def advance(self, session_id: str, *, user_id: str) -> GraphChallengeSession:
        with self._lock:
            session = self.get(session_id, user_id=user_id)
            if session.completed:
                return session
            if not session.current_round.completed:
                raise GraphChallengeStateError("Finish the current round before advancing")
            session.current_round_index += 1
            self._repository.save(session)
            return session
