from __future__ import annotations

import copy
import os
import sys
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from domain.agents.problem_solver import BaseProblemSolverAgent
from domain.problem_solving.autorater import AutoraterChatResult, AutoraterStartResult


_BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))
load_dotenv(_BACKEND_ROOT / ".env", override=False)


class AutoraterLegacyAdapter(BaseProblemSolverAgent):
    def __init__(self) -> None:
        self._module = None
        self._error: str | None = None
        self._lock = threading.Lock()

    @property
    def agent_id(self) -> str:
        return "isabella"

    @property
    def display_name(self) -> str:
        return "Isabella"

    def reset(self) -> None:
        ar = self.get_module()
        ar.reset_session()

    def get_module(self):
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

    def debug_state(self) -> dict[str, Any]:
        ar = self.get_module()
        strategy = ar.get_current_teaching_strategy()
        return {
            "debug_show_teaching_mode": getattr(ar, "DEBUG_SHOW_TEACHING_MODE", False),
            "current_problem": ar.CURRENT_PROBLEM,
            "strategy": strategy,
            "mode": ar.format_teaching_mode(strategy),
        }

    def get_progress(self) -> dict:
        ar = self.get_module()
        return {
            "current_problem": ar.CURRENT_PROBLEM,
            "total_problems": ar.TOTAL_PROBLEMS,
        }

    def start_session(self, problem_sources: list[str]) -> AutoraterStartResult:
        result, _snapshot = self.prepare_start(problem_sources)
        return result

    def reply(self, message: str, problem_sources: list[str] | None = None) -> AutoraterChatResult:
        return self.chat(message, problem_sources)

    def prepare_start(self, image_paths: list[str]) -> tuple[AutoraterStartResult, dict[str, Any]]:
        ar = self.get_module()
        ar.reset_session()

        detected, labels = ar.count_problems_in_image(image_paths=image_paths)
        if not detected or detected < 1:
            detected = 1
            labels = []

        ar.TOTAL_PROBLEMS = detected
        ar.PROBLEM_LABELS = list(labels)

        opener_strategy = ar.determine_teaching_strategy_for_problem(
            ar.CURRENT_PROBLEM,
            image_paths=image_paths,
        )
        opener_dev, opener_user = ar.build_prompt("", is_opener=True)
        opener_raw = ar.generate_ai_response(opener_dev, opener_user, image_paths=image_paths)

        if ar.get_stance_for_problem(ar.CURRENT_PROBLEM) == 2:
            opener = ar.parse_stance2_opener(opener_raw)
        else:
            opener = opener_raw

        ar.add_to_session_memory("ai", opener)
        ar.increment_turn_count(ar.CURRENT_PROBLEM)

        return (
            AutoraterStartResult(
                opener=self._with_mode_label(opener, opener_strategy) or opener,
                total_problems=detected,
                mode=self._mode_name(opener_strategy),
            ),
            self.snapshot_session(),
        )

    def restore_session(self, snapshot: dict[str, Any]) -> None:
        ar = self.get_module()
        ar.CURRENT_PROBLEM = int(snapshot["current_problem"])
        ar.TOTAL_PROBLEMS = int(snapshot["total_problems"])
        ar.PROBLEM_LABELS[:] = list(snapshot["problem_labels"])
        ar.PROBLEM_STANCE.clear()
        ar.PROBLEM_STANCE.update(snapshot["problem_stance"])
        ar.PROBLEM_TURN_COUNT.clear()
        ar.PROBLEM_TURN_COUNT.update(snapshot["problem_turn_count"])
        ar.PROBLEM_CONVERSATIONS.clear()
        ar.PROBLEM_CONVERSATIONS.update(copy.deepcopy(snapshot["problem_conversations"]))
        ar.PROBLEM_STRATEGY.clear()
        ar.PROBLEM_STRATEGY.update(snapshot["problem_strategy"])
        ar.SESSION_MEMORY[:] = copy.deepcopy(snapshot["session_memory"])

    def snapshot_session(self) -> dict[str, Any]:
        ar = self.get_module()
        return {
            "current_problem": ar.CURRENT_PROBLEM,
            "total_problems": ar.TOTAL_PROBLEMS,
            "problem_labels": list(ar.PROBLEM_LABELS),
            "problem_stance": dict(ar.PROBLEM_STANCE),
            "problem_turn_count": dict(ar.PROBLEM_TURN_COUNT),
            "problem_conversations": copy.deepcopy(ar.PROBLEM_CONVERSATIONS),
            "problem_strategy": dict(ar.PROBLEM_STRATEGY),
            "session_memory": copy.deepcopy(ar.SESSION_MEMORY),
        }

    def chat(self, user_input: str, image_paths: list[str] | None) -> AutoraterChatResult:
        ar = self.get_module()
        reply_strategy = ar.get_current_teaching_strategy()
        answer_status = ar.assess_latest_answer(user_input, image_paths=image_paths)

        if answer_status == "SOLVED":
            ai_reply = ar.build_solved_reply(
                user_input,
                ar.CURRENT_PROBLEM >= ar.TOTAL_PROBLEMS,
                image_paths=image_paths,
            )
        else:
            dev_message, user_message = ar.build_prompt(user_input, answer_status=answer_status)
            ai_reply = ar.generate_ai_response(dev_message, user_message, image_paths=image_paths)

        ai_reply_clean = ai_reply.replace("[EOP]", "").replace("[EOF]", "").strip()

        ar.add_to_session_memory("user", user_input)
        if ai_reply_clean:
            ar.add_to_session_memory("ai", ai_reply_clean)
        ar.increment_turn_count(ar.CURRENT_PROBLEM)

        problem_just_solved = answer_status == "SOLVED"
        next_opener: str | None = None
        next_mode: str | None = None

        if problem_just_solved:
            ar.record_problem_thought_async(
                problem_num=ar.CURRENT_PROBLEM,
                total_problems=ar.TOTAL_PROBLEMS,
                image_paths=image_paths,
            )
            ar.CURRENT_PROBLEM += 1

        all_done = problem_just_solved and ar.CURRENT_PROBLEM > ar.TOTAL_PROBLEMS

        if problem_just_solved and not all_done:
            next_strategy = ar.determine_teaching_strategy_for_problem(
                ar.CURRENT_PROBLEM,
                image_paths=image_paths,
            )
            opener_dev, opener_user = ar.build_prompt("", is_opener=True)
            opener_raw = ar.generate_ai_response(opener_dev, opener_user, image_paths=image_paths)
            if ar.get_stance_for_problem(ar.CURRENT_PROBLEM) == 2:
                next_opener = ar.parse_stance2_opener(opener_raw)
            else:
                next_opener = opener_raw
            ar.add_to_session_memory("ai", next_opener)
            ar.increment_turn_count(ar.CURRENT_PROBLEM)
            next_mode = self._mode_name(next_strategy)
            next_opener = self._with_mode_label(next_opener, next_strategy)

        return AutoraterChatResult(
            reply=self._with_mode_label(ai_reply_clean, reply_strategy) or ai_reply_clean,
            next_opener=next_opener,
            mode=self._mode_name(reply_strategy),
            next_mode=next_mode,
            is_done=all_done,
        )

    def _with_mode_label(self, text: str | None, strategy: str | None) -> str | None:
        if not text:
            return text
        ar = self.get_module()
        if not getattr(ar, "DEBUG_SHOW_TEACHING_MODE", False):
            return text
        return f"[mode: {ar.format_teaching_mode(strategy)}] {text}"

    def _mode_name(self, strategy: str | None) -> str | None:
        ar = self.get_module()
        if not getattr(ar, "DEBUG_SHOW_TEACHING_MODE", False):
            return None
        return ar.format_teaching_mode(strategy)
