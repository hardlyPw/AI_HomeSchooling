from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from domain.agents.conversation import GameSkillTier
from domain.games.graph_match import (
    GraphFunction,
    GraphMatchSession,
    create_agent_guess,
    graph_similarity,
)


class GraphMatchDomainTest(unittest.TestCase):
    def test_exact_function_scores_higher_than_a_distant_function(self) -> None:
        target = GraphFunction(1, 2, 1, 1)

        self.assertEqual(graph_similarity(target, target), 100.0)
        self.assertGreater(
            graph_similarity(target, GraphFunction(1, 2, 0, 1)),
            graph_similarity(target, GraphFunction(-1, 1 / 3, -2, -2)),
        )

    def test_latex_uses_fraction_and_transformation_notation(self) -> None:
        function = GraphFunction(-1, 1 / 2, -2, 1)

        self.assertEqual(
            function.to_latex(),
            r"f(x)=-\left(\frac{1}{2}\right)^{x+2}+1",
        )

    def test_agent_skill_is_fixed_and_deterministic_for_a_round(self) -> None:
        target = GraphFunction(1, 3, 0, 0)
        first = create_agent_guess(target, GameSkillTier.NORMAL, seed="round-1")
        second = create_agent_guess(target, GameSkillTier.NORMAL, seed="round-1")

        self.assertEqual(first, second)

    def test_session_contains_three_distinct_rounds(self) -> None:
        session = GraphMatchSession.create(
            user_id="demo-user",
            agent_id="jiho",
            agent_name="Jiho",
            agent_skill=GameSkillTier.NORMAL,
            seed=10,
        )

        self.assertEqual(len(session.rounds), 3)
        self.assertEqual(len({item.target for item in session.rounds}), 3)


if __name__ == "__main__":
    unittest.main()
