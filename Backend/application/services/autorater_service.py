from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Any, Literal

from domain.problem_solving.autorater import AutoraterChatResult, AutoraterStartResult
from infrastructure.adapters.isabella_solver_agent import IsabellaSolverAgent
from infrastructure.storage.temp_image_storage import TempImageStorage


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
PracticeSet = Literal["focused", "full"]


class AutoraterService:
    def __init__(
        self,
        adapter: IsabellaSolverAgent,
        storage: TempImageStorage,
        examples_dir: Path,
        focused_examples_dir: Path,
    ) -> None:
        self._adapter = adapter
        self._storage = storage
        self._example_dirs: dict[PracticeSet, Path] = {
            "focused": focused_examples_dir,
            "full": examples_dir,
        }
        self._runtime_lock = threading.RLock()
        self._preload_threads: dict[str, threading.Thread] = {}
        self._preload_cache: dict[str, dict[str, Any]] = {}
        self._session: dict[str, Any] = {
            "active": False,
            "image_path": None,
        }

    def get_legacy_module(self):
        return self._adapter.get_legacy_module()

    def debug_state(self) -> dict[str, Any]:
        with self._runtime_lock:
            return self._adapter.debug_state()

    def example_image_paths(self, practice_set: PracticeSet = "focused") -> list[Path]:
        examples_dir = self._example_dirs[practice_set]
        if not examples_dir.is_dir():
            return []

        return sorted(
            (
                path for path in examples_dir.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            ),
            key=self._natural_sort_key,
        )

    def preload_image(self, image_b64: str) -> str:
        image_bytes = self._storage.decode_base64_image(image_b64)
        cache_key = self._storage.cache_key(image_bytes)
        image_path = self._storage.write_png(image_bytes)
        return self._queue_preload(cache_key, image_path, cleanup_after=True)

    def preload_first_example_background(self, practice_set: PracticeSet = "focused") -> str:
        image_paths = self.example_image_paths(practice_set)
        if not image_paths:
            return "missing"

        first_image = image_paths[0]
        cache_key = self._storage.cache_key(first_image.read_bytes())
        return self._queue_preload(cache_key, str(first_image))

    def start(self, image_b64: str) -> AutoraterStartResult:
        image_bytes = self._storage.decode_base64_image(image_b64)
        cache_key = self._storage.cache_key(image_bytes)
        image_path = self._storage.write_png(image_bytes)

        try:
            with self._runtime_lock:
                cached = self._preload_cache.get(cache_key)
                if cached and cached.get("status") == "ready":
                    self._adapter.restore_session(cached["snapshot"])
                    result = cached["result"]
                else:
                    result, snapshot = self._adapter.prepare_start([image_path])
                    self._preload_cache[cache_key] = {
                        "status": "ready",
                        "result": result,
                        "snapshot": snapshot,
                    }

                self._cleanup_previous_image()
                self._session["image_path"] = image_path
                self._session["active"] = True
                self._session["cache_key"] = cache_key
                return result
        except Exception:
            self._storage.delete_if_exists(image_path)
            raise

    def chat(self, message: str) -> AutoraterChatResult:
        with self._runtime_lock:
            if not self._session.get("active"):
                raise ValueError("No active autorater session. Please select a problem first.")

            image_path = self._session.get("image_path")
            image_paths = [image_path] if image_path and os.path.isfile(image_path) else None
            result = self._adapter.reply(message, image_paths)
            if result.is_done:
                self._session["active"] = False
            return result

    def _queue_preload(self, cache_key: str, image_path: str, cleanup_after: bool = False) -> str:
        cached = self._preload_cache.get(cache_key)
        if cached and cached.get("status") == "ready":
            if cleanup_after:
                self._storage.delete_if_exists(image_path)
            return "ready"

        existing_thread = self._preload_threads.get(cache_key)
        if existing_thread and existing_thread.is_alive():
            if cleanup_after:
                self._storage.delete_if_exists(image_path)
            return "pending"

        def preload_worker() -> None:
            try:
                with self._runtime_lock:
                    if self._session.get("active"):
                        self._preload_cache[cache_key] = {"status": "skipped"}
                        return
                    result, snapshot = self._adapter.prepare_start([image_path])
                    self._preload_cache[cache_key] = {
                        "status": "ready",
                        "result": result,
                        "snapshot": snapshot,
                    }
            except Exception as exc:
                self._preload_cache[cache_key] = {"status": "error", "error": str(exc)}
            finally:
                if cleanup_after:
                    self._storage.delete_if_exists(image_path)

        thread = threading.Thread(
            target=preload_worker,
            daemon=True,
            name=f"autorater-preload-{cache_key[:8]}",
        )
        self._preload_threads[cache_key] = thread
        thread.start()
        return "pending"

    def _cleanup_previous_image(self) -> None:
        self._storage.delete_if_exists(self._session.get("image_path"))

    @staticmethod
    def _natural_sort_key(path: Path) -> list[int | str]:
        return [
            int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", path.name)
        ]
