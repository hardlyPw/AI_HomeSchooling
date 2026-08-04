from __future__ import annotations

import os
from pathlib import Path
import sys
import threading
from typing import Any

from dotenv import load_dotenv

from domain.problem_solving.answer_judge import AnswerStatus
from domain.problem_solving.session import ProblemSolvingSession
from domain.problem_solving.strategy import TeachingStrategy


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
load_dotenv(_BACKEND_ROOT / ".env", override=False)


class LazyAutoraterModule:
    def __init__(self) -> None:
        self._module = None
        self._error: str | None = None
        self._lock = threading.Lock()

    def get(self):
        if self._error:
            raise RuntimeError(self._error)
        if self._module is None:
            with self._lock:
                if self._error:
                    raise RuntimeError(self._error)
                if self._module is None:
                    try:
                        import main_autorater  # type: ignore[import]
                        self._module = main_autorater
                    except Exception as exc:
                        self._error = str(exc)
                        raise RuntimeError(self._error) from exc
        return self._module


class LegacyProblemSessionRepository:
    def __init__(self, module_provider: LazyAutoraterModule) -> None:
        self._module_provider = module_provider

    def reset(self) -> None:
        self._module_provider.get().reset_session()

    def configure(self, total_problems: int, labels: list[str]) -> None:
        module = self._module_provider.get()
        module.TOTAL_PROBLEMS = total_problems
        module.PROBLEM_LABELS = list(labels)

    def capture(self) -> ProblemSolvingSession:
        module = self._module_provider.get()
        return ProblemSolvingSession(
            current_problem=module.CURRENT_PROBLEM,
            total_problems=module.TOTAL_PROBLEMS,
            problem_labels=list(module.PROBLEM_LABELS),
            problem_stance=dict(module.PROBLEM_STANCE),
            problem_turn_count=dict(module.PROBLEM_TURN_COUNT),
            problem_conversations=dict(module.PROBLEM_CONVERSATIONS),
            problem_strategy=dict(module.PROBLEM_STRATEGY),
            session_memory=list(module.SESSION_MEMORY),
        )

    def restore(self, session: ProblemSolvingSession) -> None:
        module = self._module_provider.get()
        module.CURRENT_PROBLEM = session.current_problem
        module.TOTAL_PROBLEMS = session.total_problems
        module.PROBLEM_LABELS[:] = session.problem_labels
        self._replace_mapping(module.PROBLEM_STANCE, session.problem_stance)
        self._replace_mapping(module.PROBLEM_TURN_COUNT, session.problem_turn_count)
        self._replace_mapping(module.PROBLEM_CONVERSATIONS, session.problem_conversations)
        self._replace_mapping(module.PROBLEM_STRATEGY, session.problem_strategy)
        module.SESSION_MEMORY[:] = session.session_memory

    @property
    def current_problem(self) -> int:
        return int(self._module_provider.get().CURRENT_PROBLEM)

    @property
    def total_problems(self) -> int:
        return int(self._module_provider.get().TOTAL_PROBLEMS)

    def advance(self) -> None:
        module = self._module_provider.get()
        module.CURRENT_PROBLEM += 1

    @staticmethod
    def _replace_mapping(target: dict, source: dict) -> None:
        target.clear()
        target.update(source)


class LegacyTeachingStrategyPolicy:
    def __init__(self, module_provider: LazyAutoraterModule) -> None:
        self._module_provider = module_provider

    def choose(self, problem_number: int, problem_sources: list[str]) -> TeachingStrategy:
        value = self._module_provider.get().determine_teaching_strategy_for_problem(
            problem_number,
            image_paths=problem_sources,
        )
        return TeachingStrategy.from_value(value)

    def current(self) -> TeachingStrategy:
        return TeachingStrategy.from_value(
            self._module_provider.get().get_current_teaching_strategy()
        )

    def display_name(self, strategy: TeachingStrategy) -> str:
        return str(self._module_provider.get().format_teaching_mode(strategy.value))


class LegacyAnswerJudge:
    def __init__(self, module_provider: LazyAutoraterModule) -> None:
        self._module_provider = module_provider

    def assess(self, user_message: str, problem_sources: list[str] | None) -> AnswerStatus:
        value = self._module_provider.get().assess_latest_answer(
            user_message,
            image_paths=problem_sources,
        )
        return AnswerStatus.from_value(value)

    def solved_reply(
        self,
        user_message: str,
        is_last_problem: bool,
        problem_sources: list[str] | None,
    ) -> str:
        return str(self._module_provider.get().build_solved_reply(
            user_message,
            is_last_problem,
            image_paths=problem_sources,
        ))


class LegacyAutoraterPromptBuilder:
    def __init__(self, module_provider: LazyAutoraterModule) -> None:
        self._module_provider = module_provider

    def opener(self, problem_sources: list[str]) -> str:
        module = self._module_provider.get()
        developer_message, user_message = module.build_prompt("", is_opener=True)
        raw = module.generate_ai_response(
            developer_message,
            user_message,
            image_paths=problem_sources,
        )
        if module.get_stance_for_problem(module.CURRENT_PROBLEM) == 2:
            return str(module.parse_stance2_opener(raw))
        return str(raw)

    def reply(
        self,
        user_message: str,
        answer_status: AnswerStatus,
        problem_sources: list[str] | None,
    ) -> str:
        module = self._module_provider.get()
        developer_message, prompt_message = module.build_prompt(
            user_message,
            answer_status=answer_status.value,
        )
        return str(module.generate_ai_response(
            developer_message,
            prompt_message,
            image_paths=problem_sources,
        ))


class LegacyProblemInteractionLog:
    def __init__(self, module_provider: LazyAutoraterModule) -> None:
        self._module_provider = module_provider

    def record_message(self, role: str, message: str) -> None:
        self._module_provider.get().add_to_session_memory(role, message)

    def complete_turn(self) -> None:
        module = self._module_provider.get()
        module.increment_turn_count(module.CURRENT_PROBLEM)

    def record_solved_problem(self, problem_sources: list[str] | None) -> None:
        module = self._module_provider.get()
        module.record_problem_thought_async(
            problem_num=module.CURRENT_PROBLEM,
            total_problems=module.TOTAL_PROBLEMS,
            image_paths=problem_sources,
        )

    @property
    def debug_mode(self) -> bool:
        return bool(getattr(self._module_provider.get(), "DEBUG_SHOW_TEACHING_MODE", False))

    def detect_problems(self, problem_sources: list[str]) -> tuple[int, list[str]]:
        detected, labels = self._module_provider.get().count_problems_in_image(
            image_paths=problem_sources
        )
        return max(1, int(detected or 1)), list(labels or [])
