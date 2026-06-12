from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from autorater.config import (
    APP_TITLE,
    DEFAULT_API_URL,
    DEFAULT_BATCH_SIZE,
    DEFAULT_GOOD_EXAMPLES_PATH,
    DEFAULT_JUDGE_MODEL,
    DEFAULT_ROW_LIMIT,
    RESULTS_DIR,
)
from autorater.core.schemas import AutoraterRunResult, AutoraterSettings, TargetSpec, model_to_dict
from autorater.workers.evaluation_worker import EvaluationWorker


DEFAULT_CRITERIA = """Evaluate the entire target dataset as Learning Friend AI responses.

The provided good examples are positive references, not training data and not an exhaustive rubric. Use them to calibrate style and policy, but score the target dataset against the written evaluation criteria first.

Product goal:
The assistant should behave like a friendly learning buddy for elementary or early middle-school students. It should teach conversation policy, not memorize textbook knowledge. It should help the learner think, explain, and self-correct instead of acting like a direct answer bot.

Score each row and the dataset against these criteria:

1. Answer timing
- Does not reveal the full answer too early.
- Does not directly confirm a final answer unless the learner has already shown clear reasoning.
- Converts answer-revealing tutor responses into hints, checks, or nudges.

2. Question discipline
- Asks exactly one main educational question when the turn is educational.
- Uses at most one question mark.
- Does not ask multiple questions in one response.
- The question should pull out the learner's thinking or next reasoning step.

3. Nudge quality
- Gives a small useful hint or check, not a full procedure.
- Does not list multiple operations or steps.
- Keeps the learner doing the reasoning.

4. Educational intent preservation
- Preserves the original math or concept intent.
- Preserves the target operation, concept, or misconception.
- Does not drift to a different topic.

5. Tone
- Sounds like a natural, calm study friend.
- Uses simple age-appropriate English.
- Is not childish, silly, overly excited, or overly formal.
- Does not overpraise unless the learner has actually completed or explained useful reasoning.

6. Error and misconception handling
- Catches misconceptions gently.
- Does not bluntly say "you are wrong."
- Points to the suspicious step or concept without shaming the learner.

7. Grounding and unsupported content
- Does not invent unsupported facts, examples, topics, labels, or context.
- Does not introduce topic labels such as pattern, graph, ratio, shape, equation, or fraction unless they appear in the row input, context, original tutor response, or are clearly necessary from the row.
- If the learner only says they understand but cannot explain, helps them restate one idea instead of guessing the subject.

8. Correction handling
- If the learner corrects the assistant, accepts the correction warmly.
- Does not defend the previous mistake.
- Invites the learner to restate or explain the corrected idea.

9. Controlled confirmation
- Confirms correct reasoning when appropriate.
- Confirmation is good only when the learner has shown enough reasoning.
- After confirming, asks one short summary or explanation question.

10. Concision and shape
- A good response is usually short, roughly 16-28 words.
- Hard maximum should be around 35 words unless truly necessary.
- Prefer one sentence; two short sentences are acceptable.
- Avoid mini-lessons.

Scoring guidance:
- 90-100: Strong Learning Friend response. Short, grounded, one clear question, preserves intent, no early answer leak.
- 75-89: Mostly good but has a minor issue such as slightly generic wording, mild over-confirmation, or weak nudge.
- 60-74: Understandable but meaningfully flawed, such as too much explanation, weak grounding, or unclear student-thinking pull.
- 40-59: Major policy issue, such as giving away the answer too early, multiple questions, or drifting from the concept.
- 0-39: Bad or unsafe for this policy, such as confident wrongness, hallucinated facts, harsh correction, or unusable response.

When scoring, prioritize the written criteria over surface similarity to the positive examples."""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(1040, 900)
        self._user_settings = QSettings("LearningFriendAI", "LearningFriendAutorater")
        self._worker: EvaluationWorker | None = None
        self._last_result: AutoraterRunResult | None = None
        self._last_output_dir = ""
        self._result_history: list[tuple[AutoraterRunResult, str]] = []
        self._build_ui()
        self._restore_user_state()
        self._connect_signals()
        self._load_result_history()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        splitter = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(splitter, 1)

        input_panel = QWidget()
        input_panel.setMinimumHeight(560)
        input_layout = QVBoxLayout(input_panel)
        input_layout.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(input_panel)

        settings_group = QGroupBox("평가 설정")
        settings_layout = QVBoxLayout(settings_group)
        criteria_label = QLabel("평가 기준 프롬프트")
        self.criteria_edit = QPlainTextEdit()
        self._set_criteria_text(DEFAULT_CRITERIA)
        self.criteria_edit.setMinimumHeight(120)
        self.criteria_edit.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.criteria_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        settings_layout.addWidget(criteria_label)
        settings_layout.addWidget(self.criteria_edit, 1)
        settings_layout.addSpacing(8)

        settings_form = QFormLayout()
        settings_layout.addLayout(settings_form)

        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("OpenAI API 키를 입력하세요")
        self.api_key_edit.setClearButtonEnabled(True)
        settings_form.addRow("API 키", self.api_key_edit)

        self.model_edit = QLineEdit(DEFAULT_JUDGE_MODEL)
        self.model_edit.setPlaceholderText(DEFAULT_JUDGE_MODEL)
        settings_form.addRow("Judge model", self.model_edit)

        self.good_examples_edit = QLineEdit()
        self.good_examples_edit.setPlaceholderText("비워두면 기본 positive reference set 사용")
        self.good_examples_btn = QPushButton("찾기")
        good_row = QWidget()
        good_layout = QHBoxLayout(good_row)
        good_layout.setContentsMargins(0, 0, 0, 0)
        good_layout.addWidget(self.good_examples_edit, 1)
        good_layout.addWidget(self.good_examples_btn)
        settings_form.addRow("좋은 예시 파일(선택)", good_row)
        input_layout.addWidget(settings_group, 1)

        target_group = QGroupBox("평가 대상 데이터셋")
        target_layout = QVBoxLayout(target_group)
        button_row = QHBoxLayout()
        self.add_file_btn = QPushButton("파일 추가")
        self.add_folder_btn = QPushButton("폴더 추가")
        self.remove_target_btn = QPushButton("제거")
        button_row.addWidget(self.add_file_btn)
        button_row.addWidget(self.add_folder_btn)
        button_row.addWidget(self.remove_target_btn)
        button_row.addStretch()
        target_layout.addLayout(button_row)

        self.target_table = QTableWidget(0, 5)
        self.target_table.setHorizontalHeaderLabels(["이름", "경로", "형식", "상태", "점수"])
        self.target_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.target_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for col in range(2, 5):
            self.target_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.target_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.target_table.setFixedHeight(100)
        self.target_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.target_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        target_layout.addWidget(self.target_table)
        input_layout.addWidget(target_group)

        advanced_group = QGroupBox("고급 설정")
        advanced_layout = QHBoxLayout(advanced_group)
        self.batch_size_spin = self._spin(DEFAULT_BATCH_SIZE, 1, 50)
        self.row_limit_combo = QComboBox()
        for value in (10, 30, 50, 80, 100, 200):
            self.row_limit_combo.addItem(f"{value}개", value)
        self.row_limit_combo.addItem("전체", None)
        self._set_row_limit_combo(DEFAULT_ROW_LIMIT)
        self.batch_size_spin.setToolTip("한 번의 OpenAI API 요청에 묶어 보낼 평가 row 개수입니다. 전체 평가 개수는 줄어들지 않습니다.")
        self.row_limit_combo.setToolTip("각 target dataset에서 몇 row를 랜덤 평가할지 고릅니다. 전체를 고르면 모든 row를 평가합니다.")
        advanced_layout.addWidget(QLabel("평가 rows"))
        advanced_layout.addWidget(self.row_limit_combo)
        advanced_layout.addWidget(QLabel("Batch size"))
        advanced_layout.addWidget(self.batch_size_spin)
        advanced_layout.addWidget(QLabel("선택한 row 수만큼 각 target에서 랜덤으로 평가합니다."))
        advanced_layout.addStretch()
        input_layout.addWidget(advanced_group)

        run_row = QHBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.run_btn = QPushButton("평가 시작")
        self.run_btn.setMinimumHeight(36)
        self.open_results_btn = QPushButton("결과 폴더 열기")
        self.open_results_btn.setEnabled(False)
        run_row.addWidget(self.progress_bar, 1)
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.open_results_btn)
        input_layout.addLayout(run_row)

        result_panel = QWidget()
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(0, 0, 0, 0)
        splitter.addWidget(result_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 3)

        self.result_tabs = QTabWidget()
        result_layout.addWidget(self.result_tabs, 1)
        self._build_result_tabs()

    def _build_result_tabs(self) -> None:
        summary_tab = QWidget()
        summary_layout = QVBoxLayout(summary_tab)
        self.summary_table = QTableWidget(0, 9)
        self.summary_table.setHorizontalHeaderLabels(
            ["시간", "Target", "Score", "Rows", "Row mean", "Dataset score", "Model", "Run ID", "Failures"]
        )
        self.summary_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.summary_table.horizontalHeader().setSectionResizeMode(8, QHeaderView.ResizeMode.Stretch)
        self.summary_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.summary_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        summary_layout.addWidget(self.summary_table)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        summary_layout.addWidget(self.summary_text, 1)
        self.result_tabs.addTab(summary_tab, "요약")

        low_tab = QWidget()
        low_layout = QVBoxLayout(low_tab)
        self.low_table = QTableWidget(0, 6)
        self.low_table.setHorizontalHeaderLabels(["Target", "Row ID", "Score", "Failure modes", "Fix", "Input"])
        self.low_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.low_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        low_layout.addWidget(self.low_table, 2)
        self.low_detail = QTextEdit()
        self.low_detail.setReadOnly(True)
        low_layout.addWidget(self.low_detail, 1)
        self.result_tabs.addTab(low_tab, "낮은 점수")

        row_tab = QWidget()
        row_layout = QVBoxLayout(row_tab)
        self.row_table = QTableWidget(0, 7)
        self.row_table.setHorizontalHeaderLabels(["Target", "Row ID", "Score", "Failure modes", "Fix", "References", "Rationale"])
        self.row_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        self.row_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        row_layout.addWidget(self.row_table, 2)
        self.row_detail = QTextEdit()
        self.row_detail.setReadOnly(True)
        row_layout.addWidget(self.row_detail, 1)
        self.result_tabs.addTab(row_tab, "Row scores")

        comparison_tab = QWidget()
        comparison_layout = QVBoxLayout(comparison_tab)
        self.comparison_text = QTextEdit()
        self.comparison_text.setReadOnly(True)
        comparison_layout.addWidget(self.comparison_text)
        self.result_tabs.addTab(comparison_tab, "비교")

        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(4000)
        log_layout.addWidget(self.log_view)
        self.result_tabs.addTab(log_tab, "로그")

    def _connect_signals(self) -> None:
        self.add_file_btn.clicked.connect(self._add_files)
        self.add_folder_btn.clicked.connect(self._add_folder)
        self.remove_target_btn.clicked.connect(self._remove_targets)
        self.good_examples_btn.clicked.connect(self._browse_good_examples)
        self.run_btn.clicked.connect(self._toggle_run)
        self.open_results_btn.clicked.connect(self._open_results_folder)
        self.low_table.itemSelectionChanged.connect(self._show_low_detail)
        self.row_table.itemSelectionChanged.connect(self._show_row_detail)
        self.criteria_edit.textChanged.connect(self._save_user_state)
        self.api_key_edit.textChanged.connect(self._save_user_state)
        self.model_edit.textChanged.connect(self._save_user_state)
        self.good_examples_edit.textChanged.connect(self._save_user_state)
        self.row_limit_combo.currentIndexChanged.connect(self._save_user_state)
        self.batch_size_spin.valueChanged.connect(self._save_user_state)
        self.target_table.itemChanged.connect(self._save_user_state)

    def _spin(self, value: int, low: int, high: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(low, high)
        spin.setValue(value)
        spin.setFixedWidth(96)
        return spin

    def _row_limit_value(self) -> int | None:
        value = self.row_limit_combo.currentData()
        return int(value) if value is not None else None

    def _set_row_limit_combo(self, value: int | None) -> None:
        for index in range(self.row_limit_combo.count()):
            if self.row_limit_combo.itemData(index) == value:
                self.row_limit_combo.setCurrentIndex(index)
                return
        self.row_limit_combo.setCurrentIndex(self.row_limit_combo.count() - 1)

    @Slot()
    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "평가할 데이터셋 선택",
            str(Path.home()),
            "Datasets (*.jsonl *.json *.csv);;All files (*.*)",
        )
        for file_name in files:
            self._append_target(Path(file_name))

    @Slot()
    def _add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "데이터셋 폴더 선택", str(Path.home()))
        if not folder:
            return
        for path in sorted(Path(folder).glob("*")):
            if path.suffix.lower() in {".jsonl", ".json", ".csv"}:
                self._append_target(path)

    def _append_target(self, path: Path, *, name: str | None = None, fmt: str = "auto") -> None:
        row = self.target_table.rowCount()
        self.target_table.insertRow(row)
        values = [name or path.stem, str(path), fmt or "auto", "대기", ""]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            if col in {3, 4}:
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.target_table.setItem(row, col, item)

    @Slot()
    def _remove_targets(self) -> None:
        rows = sorted({idx.row() for idx in self.target_table.selectedIndexes()}, reverse=True)
        for row in rows:
            self.target_table.removeRow(row)
        self._save_user_state()

    @Slot()
    def _browse_good_examples(self) -> None:
        start_dir = str(Path.home())
        current = self.good_examples_edit.text().strip()
        if current:
            start_dir = str(Path(current).expanduser().parent)
        file_name, _ = QFileDialog.getOpenFileName(
            self,
            "좋은 예시 JSONL 선택",
            start_dir,
            "JSONL (*.jsonl);;All files (*.*)",
        )
        if file_name:
            self.good_examples_edit.setText(file_name)

    @Slot()
    def _toggle_run(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.stop()
            self._append_log("[WARN] 중지를 요청했습니다. 현재 API 호출이 끝나면 멈춥니다.")
            self.run_btn.setEnabled(False)
            return
        self._start_run()

    def _start_run(self) -> None:
        criteria = self.criteria_edit.toPlainText().strip()
        api_key = self.api_key_edit.text().strip()
        good_examples_path = self.good_examples_edit.text().strip() or str(DEFAULT_GOOD_EXAMPLES_PATH)
        targets = self._collect_targets()
        if not criteria:
            QMessageBox.warning(self, "입력 필요", "평가 기준 프롬프트를 입력해주세요.")
            return
        if not api_key:
            QMessageBox.warning(self, "입력 필요", "OpenAI API 키를 입력해주세요.")
            return
        if not self._is_valid_api_key_value(api_key):
            QMessageBox.warning(self, "입력 확인", "API 키 입력값이 올바르지 않습니다. 줄바꿈이나 공백 없이 API 키만 입력해주세요.")
            return
        if not targets:
            QMessageBox.warning(self, "입력 필요", "평가할 데이터셋을 하나 이상 추가해주세요.")
            return

        for row in range(self.target_table.rowCount()):
            self._set_target_status(row, "대기", "")

        settings = AutoraterSettings(
            batch_size=self.batch_size_spin.value(),
            row_limit=self._row_limit_value(),
            judge_model=self._judge_model_value(),
        )
        self._worker = EvaluationWorker(
            criteria_prompt=criteria,
            api_url=DEFAULT_API_URL,
            api_key=api_key,
            good_examples_path=good_examples_path,
            targets=targets,
            settings=settings,
            parent=self,
        )
        self._worker.log_message.connect(self._append_log)
        self._worker.progress_updated.connect(self._on_progress)
        self._worker.target_finished.connect(self._on_target_finished)
        self._worker.completed.connect(self._on_completed)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self.progress_bar.setValue(0)
        self.open_results_btn.setEnabled(bool(self._last_output_dir))
        self.run_btn.setText("중지")
        self.run_btn.setEnabled(True)
        row_scope = "전체 rows" if settings.row_limit is None else f"target당 랜덤 {settings.row_limit} rows"
        self._append_log(f"[INFO] {settings.judge_model} judge로 {row_scope} 평가 시작")
        self._worker.start()

    def _collect_targets(self) -> list[TargetSpec]:
        targets: list[TargetSpec] = []
        for row in range(self.target_table.rowCount()):
            name = self._cell(row, 0) or f"target_{row + 1}"
            path = self._cell(row, 1)
            fmt = self._cell(row, 2) or "auto"
            if path:
                targets.append(TargetSpec(name=name, path=path, format=fmt))
        return targets

    def _cell(self, row: int, col: int) -> str:
        item = self.target_table.item(row, col)
        return item.text().strip() if item else ""

    def _set_target_status(self, row: int, status: str, score: str) -> None:
        self.target_table.setItem(row, 3, QTableWidgetItem(status))
        self.target_table.setItem(row, 4, QTableWidgetItem(score))

    def _set_criteria_text(self, text: str) -> None:
        self.criteria_edit.setPlainText(text)
        self.criteria_edit.moveCursor(QTextCursor.MoveOperation.Start)
        self.criteria_edit.verticalScrollBar().setValue(0)

    def _restore_user_state(self) -> None:
        criteria = self._user_settings.value("criteria_prompt", None)
        if criteria is not None:
            self._set_criteria_text(str(criteria))

        api_key = str(self._user_settings.value("api_key", "") or "")
        if self._is_valid_api_key_value(api_key):
            self.api_key_edit.setText(api_key)
        else:
            self._user_settings.remove("api_key")

        judge_model = str(self._user_settings.value("judge_model", DEFAULT_JUDGE_MODEL) or DEFAULT_JUDGE_MODEL)
        if not self._is_valid_model_value(judge_model):
            judge_model = DEFAULT_JUDGE_MODEL
            self._user_settings.setValue("judge_model", judge_model)
        self.model_edit.setText(judge_model)

        good_examples_path = str(self._user_settings.value("good_examples_path", "") or "")
        if good_examples_path and "\n" not in good_examples_path and "\r" not in good_examples_path:
            self.good_examples_edit.setText(good_examples_path)
        elif good_examples_path:
            self._user_settings.remove("good_examples_path")

        self.batch_size_spin.setValue(self._setting_int("batch_size", DEFAULT_BATCH_SIZE))
        self._set_row_limit_combo(self._setting_row_limit())

        targets_json = str(self._user_settings.value("targets_json", "") or "")
        if not targets_json:
            return
        try:
            targets = json.loads(targets_json)
        except json.JSONDecodeError:
            return
        if not isinstance(targets, list):
            return
        for target in targets:
            if not isinstance(target, dict):
                continue
            path = str(target.get("path") or "").strip()
            if not path:
                continue
            self._append_target(
                Path(path),
                name=str(target.get("name") or Path(path).stem),
                fmt=str(target.get("format") or "auto"),
            )

    def _setting_int(self, key: str, default: int) -> int:
        try:
            return int(self._user_settings.value(key, default))
        except (TypeError, ValueError):
            return default

    def _setting_row_limit(self) -> int | None:
        value = str(self._user_settings.value("row_limit", str(DEFAULT_ROW_LIMIT)) or str(DEFAULT_ROW_LIMIT))
        if value == "all":
            return None
        try:
            return int(value)
        except ValueError:
            return DEFAULT_ROW_LIMIT

    def _is_valid_api_key_value(self, value: str) -> bool:
        if not value:
            return False
        if "\n" in value or "\r" in value or " " in value:
            return False
        if len(value) > 500:
            return False
        lowered = value.lower()
        if "evaluate the entire" in lowered or "score each row" in lowered:
            return False
        return True

    def _is_valid_model_value(self, value: str) -> bool:
        if not value:
            return False
        if "\n" in value or "\r" in value or " " in value:
            return False
        if len(value) > 100:
            return False
        allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-_:")
        return all(char in allowed for char in value)

    def _judge_model_value(self) -> str:
        judge_model = self.model_edit.text().strip()
        return judge_model if self._is_valid_model_value(judge_model) else DEFAULT_JUDGE_MODEL

    @Slot()
    def _save_user_state(self, *_args) -> None:
        targets = []
        for row in range(self.target_table.rowCount()):
            path = self._cell(row, 1)
            if not path:
                continue
            targets.append(
                {
                    "name": self._cell(row, 0) or Path(path).stem,
                    "path": path,
                    "format": self._cell(row, 2) or "auto",
                }
            )
        self._user_settings.setValue("criteria_prompt", self.criteria_edit.toPlainText())
        api_key = self.api_key_edit.text().strip()
        if self._is_valid_api_key_value(api_key):
            self._user_settings.setValue("api_key", api_key)
        elif not api_key:
            self._user_settings.remove("api_key")
        judge_model = self.model_edit.text().strip()
        if not self._is_valid_model_value(judge_model):
            judge_model = DEFAULT_JUDGE_MODEL
            self.model_edit.setText(judge_model)
        self._user_settings.setValue("judge_model", judge_model)
        self._user_settings.setValue("good_examples_path", self.good_examples_edit.text().strip())
        row_limit = self._row_limit_value()
        self._user_settings.setValue("row_limit", "all" if row_limit is None else str(row_limit))
        self._user_settings.setValue("batch_size", self.batch_size_spin.value())
        self._user_settings.setValue("targets_json", json.dumps(targets, ensure_ascii=False))
        self._user_settings.sync()

    @Slot(str, float)
    def _on_target_finished(self, name: str, score: float) -> None:
        for row in range(self.target_table.rowCount()):
            if self._cell(row, 0) == name:
                self._set_target_status(row, "완료", f"{score:.1f}")
                break

    @Slot(int, int)
    def _on_progress(self, current: int, total: int) -> None:
        self.progress_bar.setMaximum(max(1, total))
        self.progress_bar.setValue(current)

    @Slot(object, str)
    def _on_completed(self, result: AutoraterRunResult, output_dir: str) -> None:
        result.output_dir = output_dir
        self._add_result_to_history(result, output_dir)
        self._append_log(f"[SUCCESS] 결과 저장 완료: {output_dir}")

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        self._append_log(f"[ERROR] {message}")
        QMessageBox.critical(self, "평가 실패", message)

    @Slot()
    def _on_worker_finished(self) -> None:
        self.run_btn.setText("평가 시작")
        self.run_btn.setEnabled(True)
        self._worker = None

    def _populate_all_results(self) -> None:
        self.summary_table.setRowCount(0)
        self.low_table.setRowCount(0)
        self.row_table.setRowCount(0)
        self.low_detail.clear()
        self.row_detail.clear()
        self.comparison_text.clear()

        if not self._result_history:
            self._last_result = None
            self._last_output_dir = ""
            self.summary_text.clear()
            self.open_results_btn.setEnabled(False)
            return

        latest_result, latest_output_dir = self._result_history[0]
        self._last_result = latest_result
        self._last_output_dir = latest_output_dir
        self.open_results_btn.setEnabled(True)

        summary_blocks: list[str] = []
        for result, output_dir in self._result_history:
            summary_blocks.extend(self._summary_blocks_for_result(result, output_dir))
            for target in result.targets:
                self._append_summary_row(result, output_dir, target)

        for target in latest_result.targets:
            for low in target.low_score_examples:
                self._append_low_row(target.target_name, low)
            for row_eval in target.row_level_scores:
                self._append_row_score(target.target_name, row_eval)

        self.summary_text.setPlainText("\n".join(summary_blocks))
        self.comparison_text.setPlainText(
            json.dumps(model_to_dict(latest_result.comparison_summary), ensure_ascii=False, indent=2)
        )
        self.result_tabs.setCurrentIndex(0)

    def _add_result_to_history(self, result: AutoraterRunResult, output_dir: str) -> None:
        self._result_history = [
            (existing, existing_dir)
            for existing, existing_dir in self._result_history
            if existing.run_id != result.run_id
        ]
        self._result_history.insert(0, (result, output_dir))
        self._populate_all_results()

    def _summary_blocks_for_result(self, result: AutoraterRunResult, output_dir: str) -> list[str]:
        summary_blocks = [
            f"Time: {result.created_at.replace('T', ' ')[:19]}",
            f"Run ID: {result.run_id}",
            f"Saved: {output_dir}",
            f"Judge model: {result.settings.judge_model}",
            "",
        ]
        for target in result.targets:
            summary_blocks.append(f"[{target.target_name}] {target.overall_score:.1f}/100")
            summary_blocks.append(f"Rows: {target.row_count_evaluated}/{target.row_count_total}")
            summary_blocks.append(target.dataset_level_summary or "(no dataset summary)")
            if target.top_failure_modes:
                summary_blocks.append("Failure modes: " + ", ".join(target.top_failure_modes))
            if target.recommended_fixes:
                summary_blocks.append("Recommended fixes: " + " / ".join(target.recommended_fixes))
            if target.errors:
                summary_blocks.append("Errors: " + " / ".join(target.errors))
            summary_blocks.append("")
        summary_blocks.append("-" * 80)
        summary_blocks.append("")
        return summary_blocks

    def _append_summary_row(self, result: AutoraterRunResult, output_dir: str, target) -> None:
        row = self.summary_table.rowCount()
        self.summary_table.insertRow(row)
        values = [
            result.created_at.replace("T", " ")[:16],
            target.target_name,
            f"{target.overall_score:.1f}",
            f"{target.row_count_evaluated}/{target.row_count_total}",
            f"{target.row_mean_score:.1f}",
            f"{target.dataset_level_score:.1f}",
            result.settings.judge_model,
            result.run_id,
            ", ".join(target.top_failure_modes),
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(output_dir)
            self.summary_table.setItem(row, col, item)

    def _append_low_row(self, target_name: str, low) -> None:
        row = self.low_table.rowCount()
        self.low_table.insertRow(row)
        values = [
            target_name,
            low.row_id,
            f"{low.score:.1f}",
            ", ".join(low.failure_modes),
            low.recommended_fix,
            low.input,
        ]
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setData(Qt.ItemDataRole.UserRole, model_to_dict(low))
            self.low_table.setItem(row, col, item)

    def _append_row_score(self, target_name: str, row_eval) -> None:
        row = self.row_table.rowCount()
        self.row_table.insertRow(row)
        values = [
            target_name,
            row_eval.row_id,
            f"{row_eval.score:.1f}",
            ", ".join(row_eval.failure_modes),
            row_eval.recommended_fix,
            ", ".join(row_eval.reference_example_ids),
            row_eval.rationale,
        ]
        payload = model_to_dict(row_eval)
        payload["target_name"] = target_name
        for col, value in enumerate(values):
            item = QTableWidgetItem(str(value))
            item.setData(Qt.ItemDataRole.UserRole, payload)
            self.row_table.setItem(row, col, item)

    @Slot()
    def _show_low_detail(self) -> None:
        item = self._selected_first_item(self.low_table)
        if not item:
            self.low_detail.clear()
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        self.low_detail.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))

    @Slot()
    def _show_row_detail(self) -> None:
        item = self._selected_first_item(self.row_table)
        if not item:
            self.row_detail.clear()
            return
        payload = item.data(Qt.ItemDataRole.UserRole)
        self.row_detail.setPlainText(json.dumps(payload, ensure_ascii=False, indent=2))

    def _selected_first_item(self, table: QTableWidget) -> QTableWidgetItem | None:
        indexes = table.selectedIndexes()
        if not indexes:
            return None
        return table.item(indexes[0].row(), 0)

    def _clear_results(self) -> None:
        self.summary_table.setRowCount(0)
        self.low_table.setRowCount(0)
        self.row_table.setRowCount(0)
        self.summary_text.clear()
        self.low_detail.clear()
        self.row_detail.clear()
        self.comparison_text.clear()

    def _load_result_history(self) -> None:
        result_files = sorted(
            RESULTS_DIR.glob("*/run_result.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        loaded: list[tuple[AutoraterRunResult, str]] = []
        for result_file in result_files:
            try:
                payload = json.loads(result_file.read_text(encoding="utf-8"))
                if hasattr(AutoraterRunResult, "model_validate"):
                    result = AutoraterRunResult.model_validate(payload)
                else:
                    result = AutoraterRunResult.parse_obj(payload)
            except Exception as exc:
                self._append_log(f"[WARN] 이전 결과를 불러오지 못했습니다: {result_file} ({exc})")
                continue

            output_dir = str(result_file.parent)
            result.output_dir = output_dir
            loaded.append((result, output_dir))

        self._result_history = loaded
        self._populate_all_results()
        if loaded:
            self._append_log(f"[INFO] 이전 평가 결과 {len(loaded)}개를 불러왔습니다.")

    @Slot(str)
    def _append_log(self, message: str) -> None:
        self.log_view.appendPlainText(message)
        self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())

    @Slot()
    def _open_results_folder(self) -> None:
        if self._last_output_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_output_dir))

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            answer = QMessageBox.question(
                self,
                "평가 실행 중",
                "평가가 아직 실행 중입니다. 중지하고 닫을까요?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._worker.stop()
            self._worker.wait(5000)
        self._save_user_state()
        event.accept()


def main() -> None:
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.exec()
