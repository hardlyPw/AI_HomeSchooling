from __future__ import annotations

from pathlib import Path
import sys
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from domain.problem_solving.answer_judge import AnswerStatus
from domain.problem_solving.session import ProblemSolvingSession
from domain.problem_solving.strategy import TeachingStrategy
from infrastructure.adapters.isabella_solver_agent import IsabellaSolverAgent


class FakeModuleProvider:
    def get(self):
        return object()


class FakeSessions:
    def __init__(self) -> None:
        self.current_problem = 1
        self.total_problems = 1
        self.restored: ProblemSolvingSession | None = None

    def reset(self) -> None:
        self.current_problem = 1

    def configure(self, total_problems: int, labels: list[str]) -> None:
        self.total_problems = total_problems

    def capture(self) -> ProblemSolvingSession:
        return ProblemSolvingSession(
            current_problem=self.current_problem,
            total_problems=self.total_problems,
        )

    def restore(self, session: ProblemSolvingSession) -> None:
        self.restored = session
        self.current_problem = session.current_problem
        self.total_problems = session.total_problems

    def advance(self) -> None:
        self.current_problem += 1


class FakeStrategies:
    def choose(self, problem_number: int, problem_sources: list[str]) -> TeachingStrategy:
        return TeachingStrategy.SOCRATIC

    def current(self) -> TeachingStrategy:
        return TeachingStrategy.SOCRATIC

    def display_name(self, strategy: TeachingStrategy) -> str:
        return "Socratic"


class FakeJudge:
    status = AnswerStatus.UNCLEAR

    def assess(self, user_message: str, problem_sources: list[str] | None) -> AnswerStatus:
        return self.status

    def solved_reply(
        self,
        user_message: str,
        is_last_problem: bool,
        problem_sources: list[str] | None,
    ) -> str:
        return "[EOP]\nSolved" + ("\n[EOF]" if is_last_problem else "")


class FakePromptBuilder:
    def opener(self, problem_sources: list[str]) -> str:
        return "Where would you begin?"

    def reply(
        self,
        user_message: str,
        answer_status: AnswerStatus,
        problem_sources: list[str] | None,
    ) -> str:
        return "What does that step represent?"


class FakeInteractionLog:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.completed_turns = 0
        self.solved = 0
        self.debug_mode = False

    def detect_problems(self, problem_sources: list[str]) -> tuple[int, list[str]]:
        return 2, ["a", "b"]

    def record_message(self, role: str, message: str) -> None:
        self.messages.append((role, message))

    def complete_turn(self) -> None:
        self.completed_turns += 1

    def record_solved_problem(self, problem_sources: list[str] | None) -> None:
        self.solved += 1


class IsabellaSolverAgentTest(unittest.TestCase):
    def make_agent(self):
        sessions = FakeSessions()
        judge = FakeJudge()
        log = FakeInteractionLog()
        agent = IsabellaSolverAgent(
            module_provider=FakeModuleProvider(),
            sessions=sessions,
            strategies=FakeStrategies(),
            answer_judge=judge,
            prompt_builder=FakePromptBuilder(),
            interaction_log=log,
        )
        return agent, sessions, judge, log

    def test_start_returns_opener_and_serializable_session(self) -> None:
        agent, sessions, _judge, log = self.make_agent()

        result, snapshot = agent.prepare_start(["problem.png"])

        self.assertEqual(result.opener, "Where would you begin?")
        self.assertEqual(result.total_problems, 2)
        self.assertEqual(snapshot["current_problem"], 1)
        self.assertEqual(snapshot["total_problems"], 2)
        self.assertEqual(log.completed_turns, 1)
        self.assertEqual(sessions.total_problems, 2)

    def test_solved_reply_advances_and_opens_next_problem(self) -> None:
        agent, sessions, judge, log = self.make_agent()
        sessions.total_problems = 2
        judge.status = AnswerStatus.SOLVED

        result = agent.reply("42", ["problem.png"])

        self.assertEqual(result.reply, "Solved")
        self.assertEqual(result.next_opener, "Where would you begin?")
        self.assertFalse(result.is_done)
        self.assertEqual(sessions.current_problem, 2)
        self.assertEqual(log.solved, 1)
        self.assertEqual(log.completed_turns, 2)

    def test_final_solved_reply_ends_session_without_next_opener(self) -> None:
        agent, sessions, judge, _log = self.make_agent()
        sessions.total_problems = 1
        judge.status = AnswerStatus.SOLVED

        result = agent.reply("done", ["problem.png"])

        self.assertTrue(result.is_done)
        self.assertIsNone(result.next_opener)


if __name__ == "__main__":
    unittest.main()
