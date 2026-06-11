import base64
import copy
import hashlib
import os
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

# Resolve Backend/ root and add to sys.path so main_autorater can be imported
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Load .env from Backend/ root before main_autorater imports it
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_ROOT, ".env"), override=False)

router = APIRouter()
_EXAMPLES_DIR = Path(_ROOT) / "assets" / "Examples"
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

# ── Lazy-load autorater module so it does not block FastAPI startup ───────────
_ar = None
_ar_error: Optional[str] = None
_ar_lock = threading.Lock()
_runtime_lock = threading.RLock()
_preload_threads: dict[str, threading.Thread] = {}
_preload_cache: dict[str, dict[str, Any]] = {}


def _get_ar():
    global _ar, _ar_error
    if _ar_error:
        raise RuntimeError(_ar_error)
    if _ar is None:
        with _ar_lock:
            if _ar_error:
                raise RuntimeError(_ar_error)
            if _ar is None:
                try:
                    import main_autorater  # type: ignore[import]
                    _ar = main_autorater
                except Exception as exc:
                    _ar_error = str(exc)
                    raise RuntimeError(_ar_error) from exc
    return _ar


# ── Per-server session state (single-user app) ────────────────────────────────
_session: dict = {
    "active": False,
    "image_path": None,
}


# ── Schemas ───────────────────────────────────────────────────────────────────
class StartRequest(BaseModel):
    image_b64: str  # data-URL or raw base64 PNG from the frontend canvas crop


class PreloadRequest(BaseModel):
    image_b64: str


class StartResponse(BaseModel):
    opener: str
    total_problems: int
    mode: Optional[str] = None


class PreloadResponse(BaseModel):
    status: str


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    next_opener: Optional[str] = None
    mode: Optional[str] = None
    next_mode: Optional[str] = None
    is_done: bool


class ExampleImagesResponse(BaseModel):
    images: list[str]


# ── Helpers ───────────────────────────────────────────────────────────────────
def _decode_b64_image(image_b64: str) -> bytes:
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    return base64.b64decode(image_b64)


def _image_cache_key(img_bytes: bytes) -> str:
    return hashlib.sha256(img_bytes).hexdigest()


def _cleanup_previous_image() -> None:
    prev = _session.get("image_path")
    if prev and os.path.isfile(prev):
        try:
            os.unlink(prev)
        except OSError:
            pass


def _natural_sort_key(path: Path) -> list[int | str]:
    import re

    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.name)
    ]


def _get_example_image_paths() -> list[Path]:
    if not _EXAMPLES_DIR.is_dir():
        return []

    return sorted(
        (
            path for path in _EXAMPLES_DIR.iterdir()
            if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS
        ),
        key=_natural_sort_key,
    )


def _with_mode_label(ar, text: Optional[str], strategy: Optional[str]) -> Optional[str]:
    if not text:
        return text
    if not getattr(ar, "DEBUG_SHOW_TEACHING_MODE", False):
        return text
    return f"[mode: {ar.format_teaching_mode(strategy)}] {text}"


def _mode_name(ar, strategy: Optional[str]) -> Optional[str]:
    if not getattr(ar, "DEBUG_SHOW_TEACHING_MODE", False):
        return None
    return ar.format_teaching_mode(strategy)


def _snapshot_ar_session(ar) -> dict[str, Any]:
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


def _restore_ar_session(ar, snapshot: dict[str, Any]) -> None:
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


def _prepare_autorater_start(ar, image_paths: list[str]) -> tuple[dict[str, Any], dict[str, Any]]:
    # Reset all globals so a fresh session begins
    ar.reset_session()

    # Count problems in image (vision API)
    detected, labels = ar.count_problems_in_image(image_paths=image_paths)
    if not detected or detected < 1:
        detected = 1
        labels = []

    ar.TOTAL_PROBLEMS = detected
    ar.PROBLEM_LABELS = list(labels)

    # Generate opener for problem 1
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

    result = {
        "opener": _with_mode_label(ar, opener, opener_strategy) or opener,
        "total_problems": detected,
        "mode": _mode_name(ar, opener_strategy),
    }
    return result, _snapshot_ar_session(ar)


def _queue_preload(cache_key: str, image_path: str, cleanup_after: bool = False) -> str:
    cached = _preload_cache.get(cache_key)
    if cached and cached.get("status") == "ready":
        if cleanup_after and os.path.isfile(image_path):
            try:
                os.unlink(image_path)
            except OSError:
                pass
        return "ready"

    existing_thread = _preload_threads.get(cache_key)
    if existing_thread and existing_thread.is_alive():
        if cleanup_after and os.path.isfile(image_path):
            try:
                os.unlink(image_path)
            except OSError:
                pass
        return "pending"

    def preload_worker() -> None:
        try:
            ar = _get_ar()
            with _runtime_lock:
                if _session.get("active"):
                    _preload_cache[cache_key] = {"status": "skipped"}
                    return
                result, snapshot = _prepare_autorater_start(ar, [image_path])
                _preload_cache[cache_key] = {
                    "status": "ready",
                    "result": result,
                    "snapshot": snapshot,
                }
        except Exception as exc:
            _preload_cache[cache_key] = {"status": "error", "error": str(exc)}
        finally:
            if cleanup_after and os.path.isfile(image_path):
                try:
                    os.unlink(image_path)
                except OSError:
                    pass

    thread = threading.Thread(
        target=preload_worker,
        daemon=True,
        name=f"autorater-preload-{cache_key[:8]}",
    )
    _preload_threads[cache_key] = thread
    thread.start()
    return "pending"


def preload_first_example_background() -> str:
    image_paths = _get_example_image_paths()
    if not image_paths:
        return "missing"

    first_image = image_paths[0]
    cache_key = _image_cache_key(first_image.read_bytes())
    return _queue_preload(cache_key, str(first_image))


@router.get("/debug-mode")
def autorater_debug_mode():
    with _runtime_lock:
        ar = _get_ar()
        strategy = ar.get_current_teaching_strategy()
        return {
            "debug_show_teaching_mode": getattr(ar, "DEBUG_SHOW_TEACHING_MODE", False),
            "current_problem": ar.CURRENT_PROBLEM,
            "strategy": strategy,
            "mode": ar.format_teaching_mode(strategy),
        }


@router.get("/examples", response_model=ExampleImagesResponse)
def autorater_examples(request: Request):
    image_paths = _get_example_image_paths()
    return ExampleImagesResponse(
        images=[
            str(request.url_for("assets", path=f"Examples/{path.name}"))
            for path in image_paths
        ],
    )


# ── Endpoints (sync def → FastAPI runs these in a thread pool automatically) ──
@router.post("/preload", response_model=PreloadResponse)
def autorater_preload(req: PreloadRequest):
    img_bytes = _decode_b64_image(req.image_b64)
    cache_key = _image_cache_key(img_bytes)

    tmp: Any | None = None
    try:
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.write(img_bytes)
        tmp.close()
        status = _queue_preload(cache_key, tmp.name, cleanup_after=True)
    except Exception as exc:
        if tmp and os.path.isfile(tmp.name):
            os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=f"Failed to queue preload: {exc}")

    return PreloadResponse(status=status)


@router.post("/preload-first", response_model=PreloadResponse)
def autorater_preload_first():
    try:
        status = preload_first_example_background()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to queue first example preload: {exc}")

    return PreloadResponse(status=status)


@router.post("/start", response_model=StartResponse)
def autorater_start(req: StartRequest):
    img_bytes = _decode_b64_image(req.image_b64)
    cache_key = _image_cache_key(img_bytes)

    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(img_bytes)
    tmp.close()

    try:
        with _runtime_lock:
            ar = _get_ar()
            cached = _preload_cache.get(cache_key)
            if cached and cached.get("status") == "ready":
                _restore_ar_session(ar, cached["snapshot"])
                result = dict(cached["result"])
            else:
                result, snapshot = _prepare_autorater_start(ar, [tmp.name])
                _preload_cache[cache_key] = {
                    "status": "ready",
                    "result": result,
                    "snapshot": snapshot,
                }

            _cleanup_previous_image()
            _session["image_path"] = tmp.name
            _session["active"] = True
            _session["cache_key"] = cache_key
    except RuntimeError as exc:
        if os.path.isfile(tmp.name):
            os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=f"Autorater unavailable: {exc}")
    except Exception as exc:
        if os.path.isfile(tmp.name):
            os.unlink(tmp.name)
        raise HTTPException(status_code=500, detail=f"Failed to start autorater: {exc}")

    return StartResponse(**result)


@router.post("/chat", response_model=ChatResponse)
def autorater_chat(req: ChatRequest):
    with _runtime_lock:
        if not _session.get("active"):
            raise HTTPException(
                status_code=400,
                detail="No active autorater session. Please select a problem first.",
            )

        try:
            ar = _get_ar()
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail=f"Autorater unavailable: {exc}")

        image_path = _session.get("image_path")
        image_paths = [image_path] if image_path and os.path.isfile(image_path) else None
        user_input = req.message
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
        next_opener: Optional[str] = None
        next_mode: Optional[str] = None

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
            next_mode = _mode_name(ar, next_strategy)
            next_opener = _with_mode_label(ar, next_opener, next_strategy)

        if all_done:
            _session["active"] = False

        return ChatResponse(
            reply=_with_mode_label(ar, ai_reply_clean, reply_strategy) or ai_reply_clean,
            next_opener=next_opener,
            mode=_mode_name(ar, reply_strategy),
            next_mode=next_mode,
            is_done=all_done,
        )
