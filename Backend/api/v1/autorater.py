import base64
import os
import sys
import tempfile
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Resolve Backend/ root and add to sys.path so main_autorater can be imported
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# Load .env from Backend/ root before main_autorater imports it
from dotenv import load_dotenv  # noqa: E402
load_dotenv(os.path.join(_ROOT, ".env"), override=False)

router = APIRouter()

# ── Lazy-load autorater module so it does not block FastAPI startup ───────────
_ar = None
_ar_error: Optional[str] = None


def _get_ar():
    global _ar, _ar_error
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


class StartResponse(BaseModel):
    opener: str
    total_problems: int


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str
    next_opener: Optional[str] = None
    is_done: bool


# ── Helpers ───────────────────────────────────────────────────────────────────
def _decode_b64_image(image_b64: str) -> bytes:
    if "," in image_b64:
        image_b64 = image_b64.split(",", 1)[1]
    return base64.b64decode(image_b64)


# ── Endpoints (sync def → FastAPI runs these in a thread pool automatically) ──
@router.post("/start", response_model=StartResponse)
def autorater_start(req: StartRequest):
    try:
        ar = _get_ar()
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Autorater unavailable: {exc}")

    img_bytes = _decode_b64_image(req.image_b64)

    # Reset all globals so a fresh session begins
    ar.reset_session()

    # Write image to a temp file (kept alive for the session)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(img_bytes)
    tmp.close()

    # Clean up any previous temp file
    prev = _session.get("image_path")
    if prev and os.path.isfile(prev):
        try:
            os.unlink(prev)
        except OSError:
            pass

    _session["image_path"] = tmp.name
    _session["active"] = True

    image_paths = [tmp.name]

    # Count problems in image (vision API)
    detected, labels = ar.count_problems_in_image(image_paths=image_paths)
    if not detected or detected < 1:
        detected = 1
        labels = []

    ar.TOTAL_PROBLEMS = detected
    ar.PROBLEM_LABELS = list(labels)

    # Generate opener for problem 1
    opener_dev, opener_user = ar.build_prompt("", is_opener=True)
    opener_raw = ar.generate_ai_response(opener_dev, opener_user, image_paths=image_paths)

    if ar.get_stance_for_problem(ar.CURRENT_PROBLEM) == 2:
        opener = ar.parse_stance2_opener(opener_raw)
    else:
        opener = opener_raw

    ar.add_to_session_memory("ai", opener)
    ar.increment_turn_count(ar.CURRENT_PROBLEM)

    return StartResponse(opener=opener, total_problems=detected)


@router.post("/chat", response_model=ChatResponse)
def autorater_chat(req: ChatRequest):
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

    if problem_just_solved:
        ar.record_problem_thought_async(
            problem_num=ar.CURRENT_PROBLEM,
            total_problems=ar.TOTAL_PROBLEMS,
            image_paths=image_paths,
        )
        ar.CURRENT_PROBLEM += 1

    all_done = problem_just_solved and ar.CURRENT_PROBLEM > ar.TOTAL_PROBLEMS

    if problem_just_solved and not all_done:
        opener_dev, opener_user = ar.build_prompt("", is_opener=True)
        opener_raw = ar.generate_ai_response(opener_dev, opener_user, image_paths=image_paths)
        if ar.get_stance_for_problem(ar.CURRENT_PROBLEM) == 2:
            next_opener = ar.parse_stance2_opener(opener_raw)
        else:
            next_opener = opener_raw
        ar.add_to_session_memory("ai", next_opener)
        ar.increment_turn_count(ar.CURRENT_PROBLEM)

    if all_done:
        _session["active"] = False

    return ChatResponse(reply=ai_reply_clean, next_opener=next_opener, is_done=all_done)
