from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from application.services.autorater_service import AutoraterService
from domain.problem_solving.autorater import AutoraterChatResult


class FakeAdapter:
    def __init__(self) -> None:
        self.last_reply: tuple[str, list[str] | None] | None = None

    def reply(
        self,
        message: str,
        problem_sources: list[str] | None,
    ) -> AutoraterChatResult:
        self.last_reply = (message, problem_sources)
        return AutoraterChatResult(
            reply="Keep going",
            next_opener=None,
            mode=None,
            next_mode=None,
            is_done=False,
        )


class AutoraterServicePracticeSetTest(unittest.TestCase):
    def test_focused_and_full_examples_are_loaded_independently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            focused_dir = root / "FocusedPractice"
            full_dir = root / "Examples"
            focused_dir.mkdir()
            full_dir.mkdir()
            (focused_dir / "focused.png").write_bytes(b"focused")
            (full_dir / "example_10.png").write_bytes(b"ten")
            (full_dir / "example_2.png").write_bytes(b"two")
            (full_dir / "notes.txt").write_text("ignored", encoding="utf-8")

            service = AutoraterService(
                adapter=object(),
                storage=object(),
                examples_dir=full_dir,
                focused_examples_dir=focused_dir,
            )

            self.assertEqual(
                [path.name for path in service.example_image_paths()],
                ["focused.png"],
            )
            self.assertEqual(
                [path.name for path in service.example_image_paths("full")],
                ["example_2.png", "example_10.png"],
            )

    def test_chat_delegates_to_solver_reply(self) -> None:
        adapter = FakeAdapter()
        service = AutoraterService(
            adapter=adapter,
            storage=object(),
            examples_dir=Path("Examples"),
            focused_examples_dir=Path("FocusedPractice"),
        )
        service._session["active"] = True

        result = service.chat("16")

        self.assertEqual(result.reply, "Keep going")
        self.assertEqual(adapter.last_reply, ("16", None))


if __name__ == "__main__":
    unittest.main()
