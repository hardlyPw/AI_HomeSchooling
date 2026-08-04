from __future__ import annotations

from typing import Any

from domain.agents.problem_solver import BaseProblemSolverAgent
from domain.problem_solving.answer_judge import AnswerJudge, AnswerStatus
from domain.problem_solving.autorater import AutoraterChatResult, AutoraterStartResult
from domain.problem_solving.prompt_builder import ProblemPromptBuilder
from domain.problem_solving.session import ProblemSolvingSession
from domain.problem_solving.strategy import TeachingStrategy, TeachingStrategyPolicy
from infrastructure.adapters.legacy_autorater_components import (
    LazyAutoraterModule,
    LegacyAnswerJudge,
    LegacyAutoraterPromptBuilder,
    LegacyProblemInteractionLog,
    LegacyProblemSessionRepository,
    LegacyTeachingStrategyPolicy,
)


class IsabellaSolverAgent(BaseProblemSolverAgent):
    def __init__(
        self,
        *,
        module_provider: LazyAutoraterModule,
        sessions: LegacyProblemSessionRepository,
        strategies: TeachingStrategyPolicy,
        answer_judge: AnswerJudge,
        prompt_builder: ProblemPromptBuilder,
        interaction_log: LegacyProblemInteractionLog,
    ) -> None:
        self._module_provider = module_provider
        self._sessions = sessions
        self._strategies = strategies
        self._answer_judge = answer_judge
        self._prompt_builder = prompt_builder
        self._interaction_log = interaction_log

    @property
    def agent_id(self) -> str:
        return "isabella"

    @property
    def display_name(self) -> str:
        return "Isabella"

    def reset(self) -> None:
        self._sessions.reset()

    def get_legacy_module(self):
        return self._module_provider.get()

    def debug_state(self) -> dict[str, Any]:
        strategy = self._strategies.current()
        return {
            "debug_show_teaching_mode": self._interaction_log.debug_mode,
            "current_problem": self._sessions.current_problem,
            "strategy": strategy.value,
            "mode": self._strategies.display_name(strategy),
        }

    def get_progress(self) -> dict:
        return {
            "current_problem": self._sessions.current_problem,
            "total_problems": self._sessions.total_problems,
        }

    def start_session(self, problem_sources: list[str]) -> AutoraterStartResult:
        result, _snapshot = self.prepare_start(problem_sources)
        return result

    def prepare_start(
        self,
        problem_sources: list[str],
    ) -> tuple[AutoraterStartResult, dict[str, Any]]:
        self._sessions.reset()
        detected, labels = self._interaction_log.detect_problems(problem_sources)
        self._sessions.configure(detected, labels)
        strategy = self._strategies.choose(self._sessions.current_problem, problem_sources)
        opener = self._prompt_builder.opener(problem_sources)
        self._interaction_log.record_message("ai", opener)
        self._interaction_log.complete_turn()
        return (
            AutoraterStartResult(
                opener=self._with_mode_label(opener, strategy),
                total_problems=detected,
                mode=self._mode_name(strategy),
            ),
            self._sessions.capture().to_snapshot(),
        )

    def restore_session(self, snapshot: dict[str, Any]) -> None:
        self._sessions.restore(ProblemSolvingSession.from_snapshot(snapshot))

    def reply(
        self,
        message: str,
        problem_sources: list[str] | None = None,
    ) -> AutoraterChatResult:
        strategy = self._strategies.current()
        status = self._answer_judge.assess(message, problem_sources)
        if status == AnswerStatus.SOLVED:
            raw_reply = self._answer_judge.solved_reply(
                message,
                self._sessions.current_problem >= self._sessions.total_problems,
                problem_sources,
            )
        else:
            raw_reply = self._prompt_builder.reply(message, status, problem_sources)
        reply = raw_reply.replace("[EOP]", "").replace("[EOF]", "").strip()

        self._interaction_log.record_message("user", message)
        if reply:
            self._interaction_log.record_message("ai", reply)
        self._interaction_log.complete_turn()

        next_opener: str | None = None
        next_strategy: TeachingStrategy | None = None
        if status == AnswerStatus.SOLVED:
            self._interaction_log.record_solved_problem(problem_sources)
            self._sessions.advance()

        is_done = (
            status == AnswerStatus.SOLVED
            and self._sessions.current_problem > self._sessions.total_problems
        )
        if status == AnswerStatus.SOLVED and not is_done:
            next_strategy = self._strategies.choose(
                self._sessions.current_problem,
                problem_sources or [],
            )
            next_opener = self._prompt_builder.opener(problem_sources or [])
            self._interaction_log.record_message("ai", next_opener)
            self._interaction_log.complete_turn()
            next_opener = self._with_mode_label(next_opener, next_strategy)

        return AutoraterChatResult(
            reply=self._with_mode_label(reply, strategy),
            next_opener=next_opener,
            mode=self._mode_name(strategy),
            next_mode=self._mode_name(next_strategy) if next_strategy else None,
            is_done=is_done,
        )

    def _with_mode_label(self, text: str, strategy: TeachingStrategy) -> str:
        if not text or not self._interaction_log.debug_mode:
            return text
        return f"[mode: {self._strategies.display_name(strategy)}] {text}"

    def _mode_name(self, strategy: TeachingStrategy) -> str | None:
        if not self._interaction_log.debug_mode:
            return None
        return self._strategies.display_name(strategy)


def create_legacy_backed_isabella_agent() -> IsabellaSolverAgent:
    module_provider = LazyAutoraterModule()
    return IsabellaSolverAgent(
        module_provider=module_provider,
        sessions=LegacyProblemSessionRepository(module_provider),
        strategies=LegacyTeachingStrategyPolicy(module_provider),
        answer_judge=LegacyAnswerJudge(module_provider),
        prompt_builder=LegacyAutoraterPromptBuilder(module_provider),
        interaction_log=LegacyProblemInteractionLog(module_provider),
    )
