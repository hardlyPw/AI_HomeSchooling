from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.services.agent_catalog_service import AgentCatalogService
from application.services.graph_challenge_service import GraphChallengeService
from application.services.leaderboard_service import LeaderboardService
from application.services.memory_match_service import MemoryMatchService
from domain.agents.jiho import JIHO_DEFINITION
from domain.games.leaderboard import GameId, ScoreEntry
from domain.games.math_expression import MathExpression
from infrastructure.repositories.in_memory_agent_repository import InMemoryConversationAgentRepository
from infrastructure.repositories.in_memory_game_repository import (
    InMemoryGraphChallengeRepository,
    InMemoryMemoryMatchRepository,
    InMemoryScoreRepository,
)


class MathExpressionTest(unittest.TestCase):
    def test_evaluates_supported_school_functions(self) -> None:
        self.assertAlmostEqual(MathExpression("2*x+1").evaluate(3), 7)
        self.assertAlmostEqual(MathExpression("sin(pi/2)").evaluate(0), 1)
        self.assertAlmostEqual(MathExpression("log(e)").evaluate(0), 1)
        self.assertAlmostEqual(MathExpression("(x-1)^4").evaluate(3), 16)

    def test_rejects_unsafe_or_unknown_syntax(self) -> None:
        with self.assertRaises(ValueError):
            MathExpression("__import__('os').system('dir')")
        with self.assertRaises(ValueError):
            MathExpression("unknown(x)")


class CurrentGameServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.scores = InMemoryScoreRepository()
        self.leaderboard = LeaderboardService(self.scores)
        self.graph = GraphChallengeService(
            InMemoryGraphChallengeRepository(),
            self.leaderboard,
        )
        catalog = AgentCatalogService(
            InMemoryConversationAgentRepository((JIHO_DEFINITION,)),
            creation_service=None,  # type: ignore[arg-type]
        )
        self.memory = MemoryMatchService(
            InMemoryMemoryMatchRepository(),
            catalog,
            self.leaderboard,
        )

    def test_graph_challenge_scores_exact_functions_and_records_ranking(self) -> None:
        session = self.graph.start(user_id="demo-user", player_name="You")
        for index in range(3):
            session = self.graph.submit(
                session.id,
                user_id="demo-user",
                expression=session.current_round.target.expression.source,
                elapsed_ms=30_000,
            )
            self.assertEqual(session.current_round.attempt.graph_score, 100.0)
            self.assertEqual(session.current_round.attempt.score, 105.0)
            if index < 2:
                session = self.graph.advance(session.id, user_id="demo-user")

        self.assertTrue(session.completed)
        self.assertEqual(session.total_score, 315.0)
        entries = self.leaderboard.list(GameId.GRAPH_CHALLENGE)
        self.assertEqual(entries[0].score, 315.0)

    def test_memory_match_keeps_player_turn_after_a_pair(self) -> None:
        session = self.memory.start(user_id="demo-user", agent_id="jiho")
        self.memory.ready(session.id, user_id="demo-user")
        first_value = session.board[0]
        pair_index = next(index for index in range(1, len(session.board)) if session.board[index] == first_value)

        session = self.memory.play(
            session.id,
            user_id="demo-user",
            indices=(0, pair_index),
        )

        self.assertEqual(session.user_score, 1)
        self.assertEqual(session.phase, "player_turn")
        self.assertTrue({0, pair_index}.issubset(session.matched_indices))

    def test_memory_miss_generates_visible_agent_turns(self) -> None:
        session = self.memory.start(user_id="demo-user", agent_id="jiho")
        self.memory.ready(session.id, user_id="demo-user")
        second = next(index for index in range(1, len(session.board)) if session.board[index] != session.board[0])

        session = self.memory.play(
            session.id,
            user_id="demo-user",
            indices=(0, second),
        )

        self.assertGreaterEqual(len(session.last_agent_turns), 1)
        self.assertIn(session.phase, {"player_turn", "completed"})
        self.assertEqual(len(session.last_agent_turns[0].indices), 2)

    def test_memory_match_completion_records_ranking(self) -> None:
        session = self.memory.start(user_id="demo-user", agent_id="jiho")
        self.memory.ready(session.id, user_id="demo-user")
        positions: dict[int, list[int]] = {}
        for index, value in enumerate(session.board):
            positions.setdefault(value, []).append(index)

        for pair in positions.values():
            session = self.memory.play(
                session.id,
                user_id="demo-user",
                indices=(pair[0], pair[1]),
            )

        self.assertTrue(session.completed)
        self.assertEqual(session.user_score, 18)
        entries = self.leaderboard.list(GameId.MEMORY_MATCH)
        self.assertEqual(entries[0].score, 18)
        self.assertTrue(entries[0].detail.startswith("Won 18-"))

    def test_solo_scores_rank_highest_while_match_history_lists_newest(self) -> None:
        now = datetime.now(timezone.utc)
        older_high_score = ScoreEntry(
            game_id=GameId.MEMORY_MATCH,
            user_id="demo-user",
            player_name="You",
            score=12,
            detail="Won 12-6 vs Jiho",
            played_at=now - timedelta(hours=1),
        )
        newer_low_score = ScoreEntry(
            game_id=GameId.MEMORY_MATCH,
            user_id="demo-user",
            player_name="You",
            score=7,
            detail="Lost 7-11 vs Jiho",
            played_at=now,
        )
        self.scores.save(older_high_score)
        self.scores.save(newer_low_score)

        self.assertEqual(self.leaderboard.list(GameId.MEMORY_MATCH)[0].id, older_high_score.id)
        self.assertEqual(self.leaderboard.list_recent(GameId.MEMORY_MATCH)[0].id, newer_low_score.id)


if __name__ == "__main__":
    unittest.main()
