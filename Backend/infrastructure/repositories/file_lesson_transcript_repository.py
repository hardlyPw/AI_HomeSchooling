from __future__ import annotations

from pathlib import Path
import re
import threading

from domain.lesson.transcript import (
    LessonTranscriptRepository,
    LessonTranscriptSection,
)


class FileLessonTranscriptRepository(LessonTranscriptRepository):
    def __init__(self, script_path: Path) -> None:
        self._script_path = script_path
        self._sections: tuple[LessonTranscriptSection, ...] | None = None
        self._lock = threading.Lock()

    def context_through(self, current_video_time: float | None) -> str | None:
        if current_video_time is None or current_video_time <= 0:
            return None
        visible = [
            section
            for section in self._load_sections()
            if section.timestamp_seconds <= current_video_time
        ]
        if not visible:
            return None
        return "\n\n".join(
            f"[{section.timestamp_label}] {section.content}"
            for section in visible
        )

    def _load_sections(self) -> tuple[LessonTranscriptSection, ...]:
        if self._sections is None:
            with self._lock:
                if self._sections is None:
                    self._sections = tuple(self._parse(self._script_path))
        return self._sections

    @staticmethod
    def _parse(path: Path) -> list[LessonTranscriptSection]:
        timestamp_pattern = re.compile(r"^(\d{1,2}):(\d{2})\s*$")
        sections: list[LessonTranscriptSection] = []
        current_label: str | None = None
        current_seconds = 0
        current_text: list[str] = []

        def append_current() -> None:
            if current_label is None or not current_text:
                return
            sections.append(
                LessonTranscriptSection(
                    timestamp_seconds=current_seconds,
                    timestamp_label=current_label,
                    content=" ".join(current_text).strip(),
                )
            )

        with path.open("r", encoding="utf-8") as script:
            for line in script:
                stripped = line.strip()
                match = timestamp_pattern.match(stripped)
                if match:
                    append_current()
                    current_label = stripped
                    current_seconds = int(match.group(1)) * 60 + int(match.group(2))
                    current_text = []
                elif stripped and current_label is not None:
                    current_text.append(stripped)
        append_current()
        return sections
