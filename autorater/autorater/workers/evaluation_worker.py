from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from autorater.config import RESULTS_DIR
from autorater.core.evaluator import Autorater
from autorater.core.exporter import save_run_result
from autorater.core.schemas import AutoraterSettings, TargetSpec


class EvaluationWorker(QThread):
    log_message = Signal(str)
    progress_updated = Signal(int, int)
    target_finished = Signal(str, float)
    completed = Signal(object, str)
    failed = Signal(str)

    def __init__(
        self,
        *,
        criteria_prompt: str,
        api_url: str,
        api_key: str,
        good_examples_path: str,
        targets: list[TargetSpec],
        settings: AutoraterSettings,
        parent=None,
    ):
        super().__init__(parent)
        self.criteria_prompt = criteria_prompt
        self.api_url = api_url
        self.api_key = api_key
        self.good_examples_path = good_examples_path
        self.targets = targets
        self.settings = settings
        self._stop_requested = False

    def stop(self) -> None:
        self._stop_requested = True

    def run(self) -> None:
        try:
            autorater = Autorater(
                criteria_prompt=self.criteria_prompt,
                api_url=self.api_url,
                api_key=self.api_key,
                good_examples_path=self.good_examples_path,
                targets=self.targets,
                settings=self.settings,
                log=self.log_message.emit,
                progress=self.progress_updated.emit,
                should_stop=lambda: self._stop_requested,
            )
            result = autorater.run()
            for target in result.targets:
                self.target_finished.emit(target.target_name, target.overall_score)
            output_dir = save_run_result(result, RESULTS_DIR)
            self.completed.emit(result, str(output_dir))
        except Exception as exc:
            self.failed.emit(str(exc))

