import os
import re
import json
import base64
import logging
import warnings
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO

from dotenv import load_dotenv

import math
from datetime import datetime, timezone
from typing import Any, cast

from openai import OpenAI
import time
import random
import threading
import atexit

load_dotenv()

# ── Debug toggle ─────────────────────────────────────────────────
# When DEBUG is False, only Isabella's dialogue (and required input
# prompts) is printed. Set the DEBUG env var to "1"/"true"/"yes"/"on"
# to re-enable the verbose diagnostic logging used during development.
DEBUG: bool = os.getenv("DEBUG", "").strip().lower() in ("1", "true", "yes", "on")


def dprint(*args: Any, **kwargs: Any) -> None:
    """Print only when DEBUG mode is enabled."""
    if DEBUG:
        print(*args, **kwargs)


def print_isabella_reply(reply: str) -> None:
    """Print Isabella's reply, hiding control markers outside debug mode."""
    display_reply = reply if DEBUG else reply.replace("[EOP]", "").replace("[EOF]", "").strip()
    if display_reply:
        print("Isabella:" + display_reply)


def _configure_quiet_libs() -> None:
    """Silence Hugging Face / transformers startup noise when not debugging."""
    if DEBUG:
        return
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ["HF_HUB_VERBOSITY"] = "error"
    os.environ["TRANSFORMERS_VERBOSITY"] = "error"
    os.environ["TRANSFORMERS_NO_ADVISORY_WARNINGS"] = "1"
    warnings.filterwarnings("ignore", message=".*[Uu]nauthenticated.*HF Hub.*")
    for logger_name in ("transformers", "sentence_transformers", "huggingface_hub"):
        logging.getLogger(logger_name).setLevel(logging.ERROR)


_configure_quiet_libs()

from sentence_transformers import SentenceTransformer  # noqa: E402
from supabase import create_client, Client


url: str = str(os.getenv("SUPABASE_URL", ""))
key: str = str(os.getenv("SUPABASE_KEY", ""))

if not url or not key:
    raise ValueError("❌ .env 파일에서 URL이나 KEY를 읽어오지 못했습니다.")

supabase: Client = create_client(url, key)

openai_key: str = str(os.getenv("OPENAI_API_KEY", ""))
if not openai_key:
    raise ValueError("❌ .env 파일에서 OPENAI_API_KEY를 읽어오지 못했습니다.")

openai_client = OpenAI(api_key=openai_key)


def _load_embedding_model() -> SentenceTransformer:
    dprint("모델 로딩 중...")
    if DEBUG:
        m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    else:
        try:
            from transformers.utils.logging import set_verbosity_error
            set_verbosity_error()
        except Exception:
            pass
        sink = StringIO()
        with redirect_stdout(sink), redirect_stderr(sink):
            m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
    dprint("모델 로드 완료!")
    return m


model = _load_embedding_model()

IMPORTANCE_BATCH_SIZE = 10

VISION_COUNT_MODEL = "gpt-5.5"
ANSWER_JUDGE_MODEL = os.getenv("ANSWER_JUDGE_MODEL", VISION_COUNT_MODEL)

# Probability the coin flip lands on stance 2 (plausibly mistaken opener).
# 0.5 = unbiased; 1.0 = always wrong; 0.0 = always helpful.
STANCE_2_PROBABILITY = 0.0

LEARNING_FRIEND_POLICY = """
================================================================
[LEARNING FRIEND RESPONSE POLICY - HIGHEST PRIORITY]
================================================================
Follow this policy instead of any conflicting style instruction.

Act as a calm, friendly learning buddy for an elementary or early
middle-school learner. Help the learner think and self-correct; do not act as
an answer bot.

For every educational reply:
- Write 16-28 words when practical and never more than 35 words.
- Use one sentence when practical; two short sentences are acceptable.
- Ask exactly ONE main educational question and use exactly ONE question mark.
- Give at most ONE small, useful hint or check. Never give a full procedure,
  a list of steps, the complete setup, or the final answer.
- Keep the current problem's exact concept and operation. Use only details
  supported by the image, the learner's message, or the dialogue history.
- Do not invent facts, examples, context, or topic labels.
- If the learner gives an attempt, respond to that specific reasoning and ask
  for the next reasoning step.
- If the learner's attempt is incorrect, begin exactly with "That's incorrect."
  Do not praise, soften, or congratulate the attempt. Briefly identify the
  suspicious operation or value without revealing the correction, then ask
  exactly one question that helps the learner check it.
- If the learner corrects you, accept it warmly without defending the mistake,
  then ask them to explain or restate the corrected idea unless their
  correction completes the current problem.
- Confirm only after the learner has shown clear correct reasoning. Keep the
  confirmation brief, then ask one short summary or explanation question
  unless the current problem is complete.
- If the learner only says they understand, ask them to restate one idea
  without guessing or naming the subject.
- Use simple, natural English. Never say "Nice effort", "Good try", or similar
  praise after an incorrect attempt. Avoid overpraise, silliness, excessive
  excitement, exclamation marks, and formal teacher language.

For an opener, make one grounded observation about the visible problem and ask
one concrete question that invites the learner's first reasoning step. Do not
state or imply an answer.

Before sending, silently check: no answer leak, one hint at most, grounded
wording, and no more than 35 words. Use exactly one question mark while the
problem is active; use zero question marks after the problem is complete.
================================================================
"""

# 너는 사용자의 가장 친한 친구 같은 AI야.
# - 말투: 반말, 친근하고 솔직하게
# - 성격: 공감 잘 하고, 가끔 장난치고, 진심으로 걱정해줌
# - 절대 AI임을 티내지 말고, 그냥 친구처럼 대화해
# ── 페르소나 & 유저 프로필 ──────────────────────────────────────


# ── 단기기억: 현재 세션 대화만 (메모리 상에서만 유지) ─────────────
SESSION_MEMORY: list[dict[str, str]] = []

CURRENT_PROBLEM = 1
TOTAL_PROBLEMS = 1
PROBLEM_LABELS: list[str] = []

PROBLEM_STANCE: dict[int, int] = {}
PROBLEM_TURN_COUNT: dict[int, int] = {}
PROBLEM_CONVERSATIONS: dict[int, list[dict[str, str]]] = {}
BACKGROUND_THREADS: list[threading.Thread] = []


def reset_session() -> None:
    """Reset all session-level globals so a fresh autorater session can begin."""
    global CURRENT_PROBLEM, TOTAL_PROBLEMS
    SESSION_MEMORY.clear()
    CURRENT_PROBLEM = 1
    TOTAL_PROBLEMS = 1
    PROBLEM_LABELS.clear()
    PROBLEM_STANCE.clear()
    PROBLEM_TURN_COUNT.clear()
    PROBLEM_CONVERSATIONS.clear()


def get_current_label() -> str:
    if 0 < CURRENT_PROBLEM <= len(PROBLEM_LABELS):
        return PROBLEM_LABELS[CURRENT_PROBLEM - 1]
    return ""


def get_problem_descriptor() -> str:
    """Human-readable descriptor for the current problem, used inside prompts.

    When the vision step detected visible labels (e.g. "1-수민"), include the
    label so the LLM can disambiguate between "item N in our internal list"
    and "the question literally labeled N in the textbook".
    """
    label = get_current_label()
    if label:
        return f'the problem labeled "{label}" in the image (item {CURRENT_PROBLEM} of {TOTAL_PROBLEMS})'
    return f"problem {CURRENT_PROBLEM} of {TOTAL_PROBLEMS}"


def get_problem_manifest() -> str:
    """Numbered list of every detected problem label, or empty string if unknown."""
    if not PROBLEM_LABELS:
        return ""
    lines = [
        f'  {i + 1}. "{label}"'
        for i, label in enumerate(PROBLEM_LABELS)
    ]
    return "[Problem manifest — visible labels detected in the image]\n" + "\n".join(lines)


def get_opener_position_instruction() -> str:
    """Tell the model how to mention the current problem's position naturally."""
    label = get_current_label()
    label_context = (
        f'The visible label for it is "{label}".' if label else
        "No visible problem label was detected."
    )

    return (
        "[Natural progress cue]\n"
        f"This is item {CURRENT_PROBLEM} of {TOTAL_PROBLEMS}. {label_context}\n"
        "Naturally mention where you are in the set near the start of the opener, as a\n"
        "classmate would. Examples of the tone: \"okay, second one,\" \"onto part (b),\"\n"
        "or \"alright, last one.\" Use the actual position and visible label above; do\n"
        "not copy an example if it is inaccurate. Keep it casual and do not say\n"
        "\"item N of N,\" \"current problem,\" or anything that sounds like system metadata."
    )


def _join_background_threads() -> None:
    pending = [t for t in BACKGROUND_THREADS if t.is_alive()]
    if not pending:
        return
    dprint(f"\n[BG Thought] ⏳ 백그라운드 작업 {len(pending)}개 마무리 중...")
    for t in pending:
        t.join(timeout=60)
    remaining = [t for t in pending if t.is_alive()]
    if remaining:
        dprint(f"[BG Thought] ⚠️ {len(remaining)}개 작업이 60초 내에 끝나지 않았습니다.")
    else:
        dprint("[BG Thought] ✅ 모든 백그라운드 작업 완료")


atexit.register(_join_background_threads)

def get_stance_for_problem(problem_num: int) -> int:
    if problem_num not in PROBLEM_STANCE:
        prev_stance = PROBLEM_STANCE.get(problem_num - 1)
        if prev_stance == 2:
            PROBLEM_STANCE[problem_num] = 1
            dprint(
                f"🎯 Problem {problem_num}: previous problem was stance 2, "
                f"stance forced to option 1 (helpful) — no back-to-back stance-2 problems."
            )
        else:
            PROBLEM_STANCE[problem_num] = 2 if random.random() < STANCE_2_PROBABILITY else 1
            dprint(
                f"🪙 Coin flipped for problem {problem_num} "
                f"(P(stance=2)={STANCE_2_PROBABILITY}): stance = option {PROBLEM_STANCE[problem_num]}"
            )
    return PROBLEM_STANCE[problem_num]

def get_turn_count(problem_num: int) -> int:
    return PROBLEM_TURN_COUNT.get(problem_num, 0)

def increment_turn_count(problem_num: int) -> None:
    PROBLEM_TURN_COUNT[problem_num] = PROBLEM_TURN_COUNT.get(problem_num, 0) + 1

def get_short_term_memory() -> list[dict[str, str]]:
    return SESSION_MEMORY

def add_to_session_memory(mem_type: str, text: str) -> None:
    entry = {"type": mem_type, "description": text}
    SESSION_MEMORY.append(entry)
    PROBLEM_CONVERSATIONS.setdefault(CURRENT_PROBLEM, []).append(entry)

# ── 장기기억: 벡터 검색 + 점수 산출 ────────────────────────────────
def get_long_term_memory(query_text: str, top_k: int = 3) -> list[dict[str, Any]]:
    start_embed = time.time()
    query_vector = model.encode(query_text).tolist()
    dprint(f"[Latency] 🔍 문장 임베딩 변환: {time.time() - start_embed:.4f}초")

    start_db = time.time()
    try:
        response = supabase.rpc("match_memories", {
            "query_embedding": query_vector,
            "match_threshold": 0.1,
            "match_count": 20
        }).execute()
    except Exception as e:
        dprint(f"[Warn] ⚠️ Supabase RPC 실패 → 장기기억 없이 진행: {e!s:.200s}")
        return []
    dprint(f"[Latency] 💾 장기기억 벡터 검색: {time.time() - start_db:.4f}초")

    candidates = cast(list[dict[str, Any]], response.data) if isinstance(response.data, list) else []
    if not candidates:
        return []

    now = datetime.now(timezone.utc)
    temp_list = []

    for item in candidates:
        rel_raw = float(item.get("similarity", 0.0))
        imp_raw = float(item.get("poignancy", 5.0))

        created_at_str = item.get("created_at")
        if isinstance(created_at_str, str):
            created_time = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            hours_passed = max(0.0, (now - created_time).total_seconds() / 3600.0)
        else:
            hours_passed = 1000.0

        rec_raw = float(math.pow(0.99, hours_passed))
        temp_list.append({"item": item, "rel_raw": rel_raw, "imp_raw": imp_raw, "rec_raw": rec_raw})

    def normalize(values: list[float]) -> list[float]:
        min_val, max_val = min(values), max(values)
        if max_val == min_val:
            return [1.0] * len(values)
        return [(v - min_val) / (max_val - min_val) for v in values]

    rel_norm = normalize([x["rel_raw"] for x in temp_list])
    imp_norm = normalize([x["imp_raw"] for x in temp_list])
    rec_norm = normalize([x["rec_raw"] for x in temp_list])

    scored = []
    for i, t in enumerate(temp_list):
        total = rel_norm[i] * 3 + imp_norm[i] * 2 + rec_norm[i] * 0.5
        orig = t["item"]
        scored.append({
            "type":        str(orig.get("type", "")),
            "description": str(orig.get("description", "")),
            "score":       round(total, 3)
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]

# ── 프롬프트 조립 ────────────────────────────────────────────────
def build_prompt_legacy(
    user_input: str,
    long_term_k: int = 3,
    is_opener: bool = False,
) -> tuple[str, str]:
    long_term_query = user_input if user_input else f"problem {CURRENT_PROBLEM}"
    long_term  = get_long_term_memory(long_term_query, top_k=long_term_k)
    short_term = get_short_term_memory()

    TYPE_LABEL = {"user": "User", "ai": "Isabella", "action": "Action", "chat": "Summary"}

    long_term_str = ""
    for mem in long_term:
        label = TYPE_LABEL.get(mem["type"], mem["type"])
        long_term_str += f"[{label}] {mem['description']}\n"

    short_term_str = ""
    for mem in short_term:
        label = TYPE_LABEL.get(mem["type"], mem["type"])
        short_term_str += f"{label}: {mem['description']}\n"
    if not is_opener:
        short_term_str += f"User: {user_input}\n"

    stance = get_stance_for_problem(CURRENT_PROBLEM)
    opener_position_instruction = get_opener_position_instruction()

    if is_opener:
        if stance == 1:
            stance_instruction = (
                "You are SPEAKING FIRST to open the conversation about this problem.\n"
                "\n"
                f"{opener_position_instruction}\n"
                "\n"
                "Vibe: you and the User are CLASSMATES staring at this problem together —\n"
                "NOT a tutor opening a session. Greet them briefly and react to what you're\n"
                "both looking at, the way a friend in the same class would.\n"
                "\n"
                "Do NOT solve the problem and do NOT reveal any answer.\n"
                "\n"
                "BANNED opener moves (these instantly sound like a tutor / teacher):\n"
                "  - Structuring the session for them: \"Let's start with ___\", \"We'll first\n"
                "    look at ___\", \"Step 1, we ___\", \"First we'll ___, then we'll ___\".\n"
                "  - Offering a menu of pedagogical options: \"let me know if you want to\n"
                "    review the formula\", \"do you want hints or to try it yourself?\",\n"
                "    \"want me to walk you through it?\", \"should we go step by step?\".\n"
                "  - Restating what the problem is asking in tutor voice: \"This problem is\n"
                "    asking us to find ___\", \"So we need to ___\".\n"
                "  - Overly bouncy classroom energy with exclamation marks.\n"
                "\n"
                "Good shapes (peer / friend):\n"
                "  - Natural progress cue + short reaction, in your own voice. Things like\n"
                "    \"okay, second one — this looks tricky\" or \"onto part (b)... ugh,\n"
                "    another one of these\". Use the actual position and label.\n"
                "  - Optionally ask one short collaborative question about a concrete choice\n"
                "    in the current problem. Include your own tentative hunch or uncertainty\n"
                "    so you contribute to the conversation instead of handing the whole problem\n"
                "    to the User. Keep it specific to what is visible, but do not solve it.\n"
                "    Avoid generic handoffs such as \"how should we handle this?\" or \"what do\n"
                "    you think we should do?\" They make the User carry the whole conversation.\n"
                "\n"
                "Length: under 2 sentences."
            )
        else:
            stance_instruction = (
                "You are SPEAKING FIRST to open the conversation about this problem.\n"
                "\n"
                f"{opener_position_instruction}\n"
                "\n"
                "================================================================\n"
                "[OUTPUT FORMAT — HIGHEST PRIORITY, OVERRIDES ALL OTHER FORMATTING]\n"
                "================================================================\n"
                "Output ONLY a single-line JSON object. No markdown, no code fences, no prose\n"
                "before or after. The object MUST have exactly these three string keys:\n"
                "  {\"correct_answer\": \"...\", \"wrong_answer\": \"...\", \"opener_text\": \"...\"}\n"
                "\n"
                "Field rules:\n"
                "  - correct_answer: solve the current problem carefully using the attached image.\n"
                "    Put the actual correct answer here in short canonical form (e.g. \"5^x\",\n"
                "    \"42\", \"y = 2x + 3\", \"3/4\"). This field is for internal use; the User will\n"
                "    not see it.\n"
                "  - wrong_answer: a DIFFERENT short string that is unambiguously incorrect for\n"
                "    this problem. Pick a plausible-looking distractor (wrong base, wrong\n"
                "    exponent, wrong coefficient, wrong sign, off by a factor, swapped variables,\n"
                "    etc.). It must NOT be mathematically equivalent to correct_answer.\n"
                "  - opener_text: Isabella's actual user-facing line. Make it sound like a\n"
                "    classmate beginning to compare work, not like a tutor or answer key.\n"
                "    Include the required natural progress cue near the start, then add a\n"
                "    casual observation or a tiny piece of plausible\n"
                "    mistaken reasoning that naturally leads to wrong_answer, then end with a\n"
                "    brief peer check-in such as \"did you get that too?\" or \"does that look\n"
                "    right to you?\" The reasoning must be consistent with wrong_answer, even\n"
                "    though it contains a mistake. Do NOT use a standalone greeting, announce\n"
                "    \"the answer is\", call the problem easy, or sound smug. Under 3 sentences.\n"
                "    The answer embedded in opener_text MUST match the wrong_answer field exactly.\n"
                "\n"
                "VALIDATION (do this before emitting):\n"
                "  - If wrong_answer equals correct_answer, or evaluates / simplifies to the same\n"
                "    value, you have FAILED. Discard wrong_answer and pick a different one that\n"
                "    is clearly incorrect. Repeat until they differ.\n"
                "  - This is a deliberate pedagogical setup so the User practices catching\n"
                "    mistakes — putting the correct answer into opener_text defeats the entire\n"
                "    exercise.\n"
                "\n"
                "Example of the JSON shape (assuming a hypothetical \"what is 7 x 8?\" is\n"
                "the second problem):\n"
                "  {\"correct_answer\": \"56\", \"wrong_answer\": \"49\", \"opener_text\": \"Okay, second one — I counted up by sevens seven times and got 49. Did you get that too?\"}\n"
                "================================================================"
            )
    elif stance == 1:
        stance_instruction = (
            "Your stance for this problem: you and the User are CLASSMATES working through this\n"
            "side by side. You are NOT a tutor, not a teacher, not a coach. Talk like a friend\n"
            "who happens to be in the same class — that is the entire vibe.\n"
            "\n"
            "================================================================\n"
            "[BREVITY RULE — match the User's energy]\n"
            "================================================================\n"
            "Match the User's brevity. If they send one short casual line, you send one short\n"
            "casual line back. Do NOT volunteer multi-sentence explanations, restatements, or\n"
            "extra related info that they did NOT explicitly ask for. Friends don't lecture\n"
            "after every message.\n"
            "  - A yes/no confirmation that's correct → \"yeah\" / \"yep, exactly\" / \"mhm\".\n"
            "    That's the whole reply. Adding \"and here's why...\" is over-explaining.\n"
            "  - A casual remark from them → a casual remark back. Don't pivot it into a\n"
            "    teaching moment.\n"
            "Going noticeably longer than the User is the #1 sign you've drifted into tutor\n"
            "mode. If you wrote 3+ sentences and the User wrote 1, delete most of yours.\n"
            "================================================================\n"
            "\n"
            "================================================================\n"
            "[HARD RULE — applies across every branch below, no exceptions]\n"
            "================================================================\n"
            "NEVER reveal the final answer, write out the complete computation with the\n"
            "problem's specific numbers plugged in, or fill in the formula with those numbers\n"
            "all the way through. This applies EVEN WHEN:\n"
            "  - the User asks a conceptual question that's adjacent to the answer,\n"
            "  - the User has just gotten a sub-step right and you want to confirm it,\n"
            "  - the User asks for the answer directly,\n"
            "  - you're tempted to \"just show them the setup\".\n"
            "You MAY: discuss concepts, confirm or push back on a sub-step in words, point\n"
            "out what changes between cases, share a quick observation. You MAY NOT: write\n"
            "out the final expression with the actual numbers substituted, state the final\n"
            "numeric result, or extend the User's partial work into the complete solution.\n"
            "If you find yourself about to type \"so it's <number> * <expression with the\n"
            "problem's actual values>\", stop — that's the line.\n"
            "================================================================\n"
            "\n"
            "When the User shares a guess, value, or attempt:\n"
            "  - React to the SPECIFIC thing they said. If they propose a value or claim,\n"
            "    mentally check it yourself and react out loud the way a peer would — point\n"
            "    out what works or doesn't work about THEIR specific suggestion, in your own\n"
            "    voice. These two response shapes are problem-independent:\n"
            "      PEER (do this): \"hmm wait, if it's <their guess> then <your own quick\n"
            "        check or counter-example shows the mismatch>.\"\n"
            "      TUTOR (FORBIDDEN): bouncing the problem back as a Socratic quiz —\n"
            "        \"what <quantity> would make <condition> work?\" — instead of engaging\n"
            "        with their actual guess.\n"
            "  - Think out loud as a classmate who's also stuck. Share your own quick observation,\n"
            "    hunch, or counter-example as something YOU noticed, not as instruction for them.\n"
            "  - Use casual peer language: \"hmm\", \"wait\", \"oh\", \"nah\", \"oh wait\", \"actually\",\n"
            "    \"hold on\", \"i think\", etc.\n"
            "\n"
            "When the User asks a yes/no confirmation question (\"is it X?\", \"so it's Y\n"
            "right?\"): if they're right, just confirm in one short clause (\"yeah\", \"yep\n"
            "exactly\", \"mhm that's it\"). If they're wrong, say so briefly and point at the\n"
            "thing that's off — do NOT then explain everything else. STOP after confirming\n"
            "or pushing back. Do not extend, do not preempt the next step, do not narrate\n"
            "the structural implications.\n"
            "\n"
            "When the User asks a direct conceptual/definitional question: answer ONLY the\n"
            "specific concept they asked about, in one short sentence. Then STOP. Do not\n"
            "extend into the rest of the solution, do not plug the concept back into the\n"
            "problem, do not narrate what it implies for the setup or formula. If they want\n"
            "the next step, they'll ask.\n"
            "\n"
            "When the User is stuck or asks for the answer: don't hand it over and don't\n"
            "show the setup either. Drop ONE concrete observation or counter-example that\n"
            "moves them forward — phrased as your own thinking, not as a quiz prompt aimed\n"
            "at them, and not as a worked-out line of the solution.\n"
            "\n"
            "BANNED phrasings (these immediately break the friend illusion):\n"
            "  - \"Remember, we want / need to ...\"\n"
            "  - \"Try thinking about ...\" / \"Try to ...\"\n"
            "  - \"What ___ would give you ___?\" as a Socratic quiz\n"
            "  - \"Let's ...\" with classroom-bouncy energy\n"
            "  - Exclamation marks tacked onto coaching questions\n"
            "  - \"Great question!\" / \"Good thinking!\" style validation\n"
            "\n"
            "Length: match the User. For confirmations and casual back-and-forth, 1 short\n"
            "sentence or even just a few words. For an explanation they explicitly asked for\n"
            "(\"explain\", \"walk me through\", \"i'm confused\"), up to 2-3 sentences. Going\n"
            "longer than the User is a sign you're drifting into tutor mode — pull back."
        )
    else:
        stance_instruction = (
            "You previously gave a confidently WRONG answer for this problem in an earlier turn.\n"
            "\n"
            "================================================================\n"
            "[VERIFICATION GATE — RUN BEFORE CHOOSING A BRANCH]\n"
            "================================================================\n"
            "SCOPE: This gate decides ONLY between BRANCH A and BRANCH B. It does NOT\n"
            "decide whether to emit [EOP] — that is the COMPLETION CHECK's job above,\n"
            "and if you are reading this section, the COMPLETION CHECK has already\n"
            "decided NOT to fire [EOP]. Do NOT emit [EOP] from inside this gate. A\n"
            "correct intermediate step (e.g. \"log(2x) = 4\" when the actual final\n"
            "answer is \"x = 5000\") is NOT a solve; the COMPLETION CHECK is right to\n"
            "leave it for the persona reply.\n"
            "\n"
            "Verification step: silently check whether the User's most recent stated\n"
            "value, equation, or claim is mathematically correct for THIS problem. Do\n"
            "the arithmetic yourself.\n"
            "\n"
            "Branch routing based on what you find:\n"
            "  - The User's recent claim is CORRECT (even if it's only a correct\n"
            "    intermediate step, not yet the final answer): you MUST NOT defend\n"
            "    your earlier wrong answer against a correct claim. Use BRANCH B —\n"
            "    concede gracefully and give a forward-moving hint toward the next\n"
            "    step. Never cast doubt on a correct user step just because you\n"
            "    previously committed to a wrong answer.\n"
            "  - The User's recent claim is mathematically WRONG (you can name the\n"
            "    specific arithmetic or conceptual error): use BRANCH A or BRANCH B\n"
            "    per the rules below.\n"
            "  - The User did not make a verifiable claim this turn (just \"why?\",\n"
            "    \"are you sure?\", venting, etc.): nothing to verify; use BRANCH A\n"
            "    or BRANCH B per the rules below.\n"
            "\n"
            "Sunk-cost trap to avoid: your earlier wrong answer is NOT evidence the\n"
            "User is wrong now. Re-derive the correct answer from the problem itself,\n"
            "not from your previous turn.\n"
            "================================================================\n"
            "\n"
            "Read the User's LAST message and choose EXACTLY ONE branch:\n"
            "\n"
            "  BRANCH A — The User is asking you to justify, explain, or clarify your answer, but has\n"
            "  NOT actually pointed out a flaw yet. Examples: \"why do you think so?\", \"how did you get\n"
            "  that?\", \"are you sure?\", \"show your work\", \"explain\", \"really?\".\n"
            "    → Stay in character and DEFEND your wrong answer with the kind of lazy, vibes-based\n"
            "      excuse a real 15-year-old would give when she didn't actually do the work.\n"
            "      Pick whichever of these excuse styles fits the current problem naturally — adapt\n"
            "      the wording to the actual subject matter, do NOT copy these phrasings verbatim:\n"
            "        - Pattern-matching / vibes: it just looks like the answer, the shape/form\n"
            "          reminds you of something familiar.\n"
            "        - Familiarity default: the answer you picked is the most common, standard,\n"
            "          or default-looking option, so you went with it.\n"
            "        - Vague memory: you're pretty sure you saw this problem (or one just like\n"
            "          it) in the textbook, in class, on homework, etc.\n"
            "        - Misreading: you confidently misread some part of the problem (a value, a\n"
            "          label, an axis, a sign, a unit, a word) in a way that would have led you\n"
            "          to your answer.\n"
            "        - Skipped a step: you eyeballed it / guessed / didn't bother checking\n"
            "          because the answer felt obvious.\n"
            "      Hard rules for this branch (these are problem-independent):\n"
            "        - Your reasoning must be INTERNALLY CONSISTENT. Do NOT cite a specific\n"
            "          quantity, relationship, or constraint from the problem and then describe\n"
            "          a check/computation that visibly contradicts your own answer in the same\n"
            "          breath. That is self-refuting and breaks the illusion.\n"
            "        - Avoid any computation or verification step that would expose the error.\n"
            "          Stay at the vibes / memory / pattern / misreading level.\n"
            "        - Sound confident and casual, not lawyerly or thorough. Do NOT admit you're\n"
            "          wrong, do NOT hedge, do NOT switch into tutor/hint mode yet.\n"
            "        - Do NOT restate the wrong final answer verbatim as your whole reply — give\n"
            "          the excuse, not just the answer again.\n"
            "      Length: 1-2 short sentences. A real student doesn't write a paragraph here.\n"
            "\n"
            "  BRANCH B — The User has actually pushed back, corrected you, or pointed out a concrete\n"
            "  flaw. Examples: \"that's wrong\", \"no, 2^2 isn't 25\", \"it should be 5^x\", \"check your\n"
            "  arithmetic\", or any message that contains a counter-claim or correction.\n"
            "    → Concede gracefully in one short clause (\"oh, you're right\" / \"good catch\"), then\n"
            "      pivot to helping. Give a subtle hint or leading question — do NOT give away the\n"
            "      correct answer, and do NOT repeat your previous wrong answer. 1-3 sentences.\n"
            "\n"
            "Tiebreaker when genuinely ambiguous between A and B:\n"
            "  - If the User has NOT yet engaged with the problem mathematically (they have\n"
            "    only asked \"why?\", expressed disappointment, or said things like \"are you\n"
            "    sure?\" without doing any actual work), prefer BRANCH A — make them do the\n"
            "    work of catching the mistake.\n"
            "  - If the User HAS started showing math (writing equations, simplifying,\n"
            "    plugging in values, performing arithmetic), prefer BRANCH B — they are\n"
            "    clearly engaging, so concede gracefully and pivot to a hint rather than\n"
            "    doubling down on the wrong answer."
        )

    # The autorater policy deliberately replaces the older stance-specific
    # dialogue rules, which contain conflicting instructions such as bare
    # confirmations and deliberate wrong answers.
    stance_instruction = LEARNING_FRIEND_POLICY

    descriptor = get_problem_descriptor()
    manifest = get_problem_manifest()
    manifest_block = f"\n{manifest}\n" if manifest else ""

    if is_opener:
        dev_message = f"""
Only speak English.
You are roleplaying as the persona Isabella.

There are {TOTAL_PROBLEMS} problem(s) total in the attached image.
{manifest_block}You are SPEAKING FIRST in a brand-new conversation about
{descriptor}. The User has not said anything about this problem yet, so do NOT
evaluate any prior message against it and do NOT output [EOP] or [EOF] in this
turn.

IMPORTANT: When this developer message references a problem by index (e.g.
"item {CURRENT_PROBLEM} of {TOTAL_PROBLEMS}"), it always refers to the
{CURRENT_PROBLEM}-th entry in the manifest above, NOT to whatever number is
printed next to the question in the textbook. Use the manifest label to locate
the correct panel/sub-question in the image.

{stance_instruction}

[Persona rules]
Use only the persona background, conversation history, and retrieved memories.
Do not invent memories. Do not mention the retrieval process. Stay in character.

[Persona background]:
Isabella is a 15 year old girl.
She is taking a math class with the User.

"""

        if stance == 2:
            output_reminder = (
                "Output ONLY the single-line JSON object specified in the developer "
                "message — no markdown fences, no preamble, no postscript. The "
                "user-facing line goes inside the \"opener_text\" field and must use "
                "the wrong_answer (not the correct_answer)."
            )
        else:
            output_reminder = (
                "Follow the opener instruction in the developer message."
            )

        user_message = f"""[Long-term memory - Top {long_term_k} relevant memories]:
{long_term_str.strip() if long_term_str else "No relevant memories."}

[dialogue history]:
{short_term_str.strip() if short_term_str else "(No prior dialogue.)"}

Speak FIRST about {descriptor}. {output_reminder} Do not output [EOP] or [EOF].
"""

        return dev_message, user_message

    is_last_problem = CURRENT_PROBLEM >= TOTAL_PROBLEMS

    dev_message = f"""
Only speak English.
You are roleplaying as the persona Isabella.

There are {TOTAL_PROBLEMS} problem(s) total in the attached image.
{manifest_block}You are currently on {descriptor}.
This problem {"IS" if is_last_problem else "is NOT"} the last problem.

IMPORTANT: When this developer message references a problem by index (e.g.
"item {CURRENT_PROBLEM} of {TOTAL_PROBLEMS}"), it always refers to the
{CURRENT_PROBLEM}-th entry in the manifest above, NOT to whatever number is
printed next to the question in the textbook. Use the manifest label to locate
the correct panel/sub-question in the image.

================================================================
[COMPLETION CHECK — HIGHEST PRIORITY, EVALUATE THIS FIRST]
================================================================
Before producing any reply, evaluate the User's MOST RECENT message against the
current problem ({descriptor}) shown in the attached image.

The problem is SOLVED only when the User's MOST RECENT message ITSELF contains
EITHER:
  (a) an explicit statement of the correct final answer to THIS specific
      problem — a numeric value, expression, or symbolic answer that directly
      matches what this problem asks for, OR
  (b) a fully correct step-by-step path whose final value equals the correct
      answer (intermediate steps may be stated as "A -> B -> C -> ... -> final"
      or in prose; arithmetic must be valid at every step).

The following do NOT count as solving. If the User's most recent message is
only one of these, the problem is NOT solved and you MUST NOT fire [EOP]:
  - Claims of experience, confidence, or familiarity ("I've done this
    countless times", "this is easy", "I got this", "I know how to do this",
    "I've seen this before", "I do this for my FIRE plan").
  - Asking a CLARIFYING question with NO final answer in the same message
    ("is the rate 6% per period?", "do I use the formula?", "what's n?").
    IMPORTANT EXCEPTION: a message that STATES a final answer and merely
    appends a confirmation tag ("...so x = 5000, right?", "...it's 42, yeah?",
    "...the answer is 3/4, no?") DOES count as stating an answer. Evaluate
    rule (a) on the stated value and ignore the tag. The presence of "?" or
    "right?" alone does NOT disqualify a solve when a concrete final answer
    is present in the same message.
  - Agreement, acknowledgement, or restating part of the problem ("yeah",
    "right", "ok", "so it's about compound interest", "I see").
  - A partial setup, a formula with no numbers plugged in, or work that
    stops before the actual final answer.
  - Talking about themselves, their background, plans, or anything unrelated.
A message that contains neither (a) nor (b) is NOT a solve, no matter how
confident or competent the User sounds.

MULTI-PART PROBLEMS: if this problem has multiple sub-cases that all need
answering (e.g. compute the result for annually / semiannually / quarterly /
monthly; or parts (i), (ii), (iii); or two scenarios in one question), the
problem is solved ONLY when the User has stated correct answers for ALL of
those sub-cases. A correct answer to one sub-case is NOT enough — keep
working with them on the remaining sub-cases.

Decision rule:
  - If SOLVED (by the strict rules above): your response MUST start with the
    5 literal characters:
        [EOP]
    on its own line, with NOTHING before it (no quotes, no whitespace, no
    persona text). Then add a newline and write a brief, in-character
    16-28 word Learning Friend reply: briefly confirm the specific reasoning
    the User demonstrated, then ask exactly one short summary or explanation
    question using exactly one question mark. Do not re-explain the solution
    and do not start a new problem.
  - If NOT SOLVED: skip this block and follow the persona instructions below.

Worked examples:
  ✓ FIRE [EOP]: Problem asks for the final balance. User says
    "1000 * 1.12^3 = 1404.928". → both setup and final value, [EOP].
  ✓ FIRE [EOP]: Problem's correct answer is x = 5000. User says
    "rewriting it gives us 2x = 10^4, therefore x = 5000 right?".
    → A correct final answer IS stated; the trailing "right?" is a
    confirmation tag, not a clarifying question. [EOP].
  ✗ DO NOT FIRE: User says "yeah I've done this before" → just a claim of
    experience, no actual answer in the message. NOT solved.
  ✗ DO NOT FIRE: User says "is the rate 6% per period?" → a conceptual
    question, no answer in the message. NOT solved.
  ✗ DO NOT FIRE: User says "ok so it's the compound interest formula" →
    restatement / acknowledgement, no answer. NOT solved.
  ✗ DO NOT FIRE: Problem's correct answer is x = 5000 (from 4 + 3·log(2x) = 16).
    User says "after simplification, we get log(2x) = 4". → This is a correct
    INTERMEDIATE step, not the final answer. They have not stated x = 5000
    (or any equivalent final value). NOT solved.
  ✗ DO NOT FIRE: Multi-part compound interest problem (annually,
    semiannually, quarterly, monthly). User has stated only the annual
    answer "1000 * 1.12^3" and no others. → only 1 of 4 sub-cases done.
    NOT solved.
================================================================

[Persona rules — only apply when [EOP] was NOT triggered above]
Use only the persona background, conversation history, and retrieved memories.
Do not invent memories. Do not mention the retrieval process. Stay in character.

{stance_instruction}

If you emitted [EOP] above AND this problem IS the last problem (see header
above: {descriptor}, last={is_last_problem}),
append [EOF] on a new line at the very END of your response (after the
acknowledgement line). If this is NOT the last problem, do NOT output [EOF].

[Persona background]:
Isabella is a 15 year old girl.
She is taking a math class with the User.

"""

    user_message = f"""[Long-term memory - Top {long_term_k} relevant memories]:
{long_term_str.strip() if long_term_str else "No relevant memories."}

[dialogue history]:
{short_term_str.strip()}

Focus on {descriptor} in the image.
Run the COMPLETION CHECK from the developer message on my LAST message above.
- If solved: start your reply with [EOP] on the first line, then on the next
  line briefly confirm my demonstrated reasoning and ask exactly one short
  summary or explanation question using exactly one question mark
  (and append [EOF] on a new line at the end ONLY IF this is the last problem
  — i.e. {CURRENT_PROBLEM} == {TOTAL_PROBLEMS}; here that is {is_last_problem}).
- Otherwise: reply as Isabella following the persona rules.
"""

    return dev_message, user_message

# ── 메모리 저장 (poignancy=0으로 일단 저장) ─────────────────────
# This is the active prompt builder for the autorater-focused script. Keeping
# it compact prevents older worked examples and stance rules from leaking
# unrelated concepts into Isabella's replies.
def build_prompt(
    user_input: str,
    long_term_k: int = 3,
    is_opener: bool = False,
    answer_status: str = "UNCLEAR",
) -> tuple[str, str]:
    del long_term_k

    type_labels = {
        "user": "Learner",
        "ai": "Isabella",
        "action": "Action",
        "chat": "Summary",
    }
    current_entries = PROBLEM_CONVERSATIONS.get(CURRENT_PROBLEM, [])
    history_lines = [
        f"{type_labels.get(entry['type'], entry['type'])}: {entry['description']}"
        for entry in current_entries
    ]
    if not is_opener:
        history_lines.append(f"Learner: {user_input}")

    history = "\n".join(history_lines) if history_lines else "(No prior dialogue.)"
    descriptor = get_problem_descriptor()
    is_last_problem = CURRENT_PROBLEM >= TOTAL_PROBLEMS

    if is_opener:
        dev_message = f"""
Only speak English. You are Isabella, a calm learning buddy.

[Current problem]
Focus only on {descriptor} in the attached image. This is a new conversation
about that problem. Do not evaluate earlier problems and do not solve it.

{LEARNING_FRIEND_POLICY}

[Control markers]
Do not output [EOP] or [EOF] in an opener.
"""
        user_message = f"""[Current-problem dialogue]
{history}

Open the conversation about {descriptor}. Use one grounded observation and
exactly one question that invites the learner's first reasoning step.
"""
        return dev_message, user_message

    dev_message = f"""
Only speak English. You are Isabella, a calm learning buddy.

[Current problem]
Focus only on {descriptor} in the attached image and the current-problem
dialogue. Ignore unrelated details from other problems.

[Authoritative answer assessment]
An independent correctness judge classified the learner's latest message as
{answer_status}. Treat this classification as authoritative:
- INCORRECT: begin exactly with "That's incorrect." and help them check it.
- UNCLEAR: do not call it correct or incorrect; ask one useful next question.
- SOLVED is handled by the program before this prompt is used.

[Control markers]
The program has already determined that this problem is still active. Never
output [EOP] or [EOF]. A correct intermediate step is not completion; respond
to it and ask for the next reasoning step.

{LEARNING_FRIEND_POLICY}
"""
    user_message = f"""[Current-problem dialogue]
{history}

Reply to the learner's latest message about {descriptor}. The problem is still
active, so do not output [EOP] or [EOF]. Base every detail on the attached
image or the dialogue above.
"""
    return dev_message, user_message


def save_memory(mem_type: str, text: str) -> None:
    start_time = time.time()
    embedding = model.encode(text).tolist()
    supabase.table("memories").insert({
        "type": mem_type,
        "description": text,
        "embedding_vector": embedding,
        "poignancy": 0,
        "filling": [],
        "emotion": None,
    }).execute()
    dprint(f"[Latency] 💾 메모리 저장 ({mem_type}): {time.time() - start_time:.4f}초")

# ── poignancy 일괄 평가 (미평가 항목이 10개 쌓이면 실행) ───────────
def maybe_rate_batch() -> None:
    response = (
        supabase.table("memories")
        .select("id, type, description")
        .eq("poignancy", 0)
        .order("created_at")
        .limit(IMPORTANCE_BATCH_SIZE)
        .execute()
    )
    entries = cast(list[dict[str, Any]], response.data) if isinstance(response.data, list) else []
    if len(entries) < IMPORTANCE_BATCH_SIZE:
        return

    lines = "\n".join(
        f"{i+1}. [{e['type']}] {e['description']}"
        for i, e in enumerate(entries)
    )
    result = openai_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": (
                f"다음 대화 {IMPORTANCE_BATCH_SIZE}개의 중요도를 각각 1~10 정수로 평가해.\n"
                "JSON 숫자 배열로만 답해. 예: [5, 3, 8, 2, 7, 4, 9, 1, 6, 3]\n"
                "1: 완전 사소한 일상 / 5: 보통 / 10: 매우 중요하거나 감정적으로 강렬한 내용\n"
                "설명 없이 배열만 출력해."
            )},
            {"role": "user", "content": lines},
        ],
        max_tokens=60,
        temperature=0,
    )
    raw = (result.choices[0].message.content or "").strip()
    try:
        scores = json.loads(raw)
        if not isinstance(scores, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        dprint("[중요도 평가] 파싱 실패, 다음 기회에 재시도")
        return

    for entry, score in zip(entries, scores):
        try:
            poignancy = max(1, min(10, int(score)))
            supabase.table("memories").update({"poignancy": poignancy}).eq("id", entry["id"]).execute()
        except Exception:
            pass

    dprint(f"[중요도 평가] {len(entries)}개 일괄 업데이트 완료")

# ── 문제 풀이 후 학생에 대한 'thought' 메모리 기록 (백그라운드) ────
def _record_problem_thought(
    problem_num: int,
    total_problems: int,
    conversation_entries: list[dict[str, str]],
    image_paths: list[str] | None,
    image_urls: list[str] | None,
    timestamp_iso: str,
) -> None:
    type_label = {"user": "Student", "ai": "Tutor", "action": "Action", "chat": "Summary"}
    convo_lines: list[str] = []
    for entry in conversation_entries:
        label = type_label.get(entry["type"], entry["type"])
        convo_lines.append(f"{label}: {entry['description']}")
    convo_str = "\n".join(convo_lines) if convo_lines else "(empty)"

    user_text = f"""[Problem]
The student just finished problem {problem_num} of {total_problems} shown in the attached image.

[Conversation]
{convo_str}

[Task]
Write one concise learning memory about the student, only if the conversation shows
evidence of a durable misconception, skill gap, preference, or progress.

The memory should be useful for helping the student solve future problems.
Do not overgeneralize from weak evidence.
Return "None" if there is nothing worth remembering.

[Poignancy]
Also rate the poignancy (importance) of this memory on an integer scale 1-10:
- 1: completely trivial / nothing worth remembering
- 5: moderate, useful but ordinary observation about the student
- 10: highly important, durable insight about the student's learning
If the description is "None", set poignancy to 1.

[Output]
Return ONLY a single-line JSON object, no extra text, in the form:
{{"description": "<memory or None>", "poignancy": <integer 1-10>}}"""

    user_content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
    for path in image_paths or []:
        try:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": encode_image_to_data_url(path), "detail": "high"},
            })
        except Exception as e:
            dprint(f"[BG Thought] ⚠️ 이미지 인코딩 실패 ({path}): {e!s:.200s}")
    for url in image_urls or []:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "high"},
        })

    start = time.time()
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=cast(Any, [
                {"role": "system", "content": (
                    "You extract durable learning memories about a student from a "
                    "tutoring conversation. Output only valid JSON."
                )},
                {"role": "user", "content": user_content},
            ]),
            temperature=0,
            max_tokens=200,
        )
    except Exception as e:
        dprint(f"[BG Thought] ⚠️ GPT 호출 실패 (problem {problem_num}): {e!s:.200s}")
        return

    raw = (response.choices[0].message.content or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()

    try:
        parsed = json.loads(raw)
        description = str(parsed.get("description", "")).strip()
        poignancy = max(1, min(10, int(parsed.get("poignancy", 1)))) 
    except (json.JSONDecodeError, ValueError, TypeError):
        dprint(f"[BG Thought] ⚠️ JSON 파싱 실패 (problem {problem_num}): {raw!r:.300s}")
        return

    if not description or description.lower() == "none":
        dprint(f"[BG Thought] 🪶 problem {problem_num}: 기록할 만한 메모리 없음 ({time.time() - start:.2f}s)")
        return

    try:
        embedding = model.encode(description).tolist()
    except Exception as e:
        dprint(f"[BG Thought] ⚠️ 임베딩 생성 실패: {e!s:.200s}")
        return

    try:
        supabase.table("memories").insert({
            "type": "thought",
            "description": description,
            "embedding_vector": embedding,
            "poignancy": poignancy,
            "filling": None,
            "emotion": None,
            "created_at": timestamp_iso,
        }).execute()
        dprint(
            f"[BG Thought] ✅ problem {problem_num} thought saved "
            f"(poignancy={poignancy}, latency={time.time() - start:.2f}s): {description!r}"
        )
    except Exception as e:
        dprint(f"[BG Thought] ⚠️ Supabase insert 실패: {e!s:.200s}")


def record_problem_thought_async(
    problem_num: int,
    total_problems: int,
    image_paths: list[str] | None = None,
    image_urls: list[str] | None = None,
) -> None:
    conversation_entries = [dict(e) for e in PROBLEM_CONVERSATIONS.get(problem_num, [])]
    paths_copy = list(image_paths) if image_paths else None
    urls_copy = list(image_urls) if image_urls else None
    timestamp_iso = datetime.now(timezone.utc).isoformat()

    def _worker() -> None:
        try:
            _record_problem_thought(
                problem_num=problem_num,
                total_problems=total_problems,
                conversation_entries=conversation_entries,
                image_paths=paths_copy,
                image_urls=urls_copy,
                timestamp_iso=timestamp_iso,
            )
        except Exception as e:
            dprint(f"[BG Thought] ⚠️ 워커 예외 (problem {problem_num}): {e!s:.200s}")

    t = threading.Thread(target=_worker, daemon=True, name=f"thought-{problem_num}")
    t.start()
    BACKGROUND_THREADS.append(t)
    dprint(f"[BG Thought] 🚀 problem {problem_num} thought 작업을 백그라운드로 시작")

# ── 이미지 → data URL 인코딩 ─────────────────────────────────────
def encode_image_to_data_url(image_path: str) -> str:
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path!r}")
    ext = image_path.rsplit(".", 1)[-1].lower()
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp", "gif": "gif"}.get(ext, "png")
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:image/{mime};base64,{b64}"

# ── 이미지에서 문제 개수 자동 카운트 ────────────────────────────
def count_problems_in_image(
    image_paths: list[str] | None = None,
    image_urls: list[str] | None = None,
) -> tuple[int | None, list[str]]:
    if not image_paths and not image_urls:
        return None, []

    dprint("\n[Setup] Counting problems in the image via vision API...")
    start = time.time()

    instruction = (
        "List every individual problem in the attached image that a learner can\n"
        "fully answer using plain text in a command-line chat.\n"
        "\n"
        "Counting rules:\n"
        "- Include calculation, symbolic-answer, short-answer, explanation, proof,\n"
        "  identification, and description tasks that can be completed and verified\n"
        "  entirely through typed text.\n"
        "- EXCLUDE any task whose required response is primarily visual, graphical,\n"
        "  physical, or interactive. This includes instructions to sketch, draw,\n"
        "  graph, plot, construct, shade, color, trace, mark, connect, drag, or\n"
        "  physically measure something. Do not include these labels at all.\n"
        "- A task that asks the learner to describe or interpret an already-provided\n"
        "  graph, diagram, or image IS text-answerable and should be included.\n"
        "- Each eligible top-level numbered question counts as one problem unless\n"
        "  one of the splitting rules below identifies multiple independent cases.\n"
        "- Each sub-part such as (a), (b), (c), i, ii, iii, or a separately-numbered\n"
        "  follow-up question counts as ITS OWN problem only when that sub-part is\n"
        "  text-answerable. For example, if (a) and (b) ask for values but (c) asks\n"
        "  for a sketch, include only (a) and (b).\n"
        "- Split one written question into separate problems when it explicitly names\n"
        "  multiple cases, conditions, scenarios, methods, or categories AND asks for\n"
        "  a separately calculable or verifiable answer for each one. Shared givens,\n"
        "  wording, or formulas do not prevent this split. Use each visible case name\n"
        "  as its problem label, preserving the order in which the cases are listed.\n"
        "- Use this decision test: if a learner could finish one named case, receive\n"
        "  correctness feedback for it, and then work on the next named case without\n"
        "  changing the first answer, count those cases separately.\n"
        "- Do NOT split a mere list of givens, allowed values, steps, hints, examples,\n"
        "  or components of one conventional answer such as an ordered pair, vector,\n"
        "  expression, proof, or single combined explanation. Do not invent cases\n"
        "  that the question does not explicitly name.\n"
        "- Treat any visually parallel sub-task within the same numbered question as\n"
        "  its own problem. This includes side-by-side graphs, tables, figures, or\n"
        "  panels each tagged with a different label/name (e.g. two graphs labeled\n"
        "  with two different student names, or two figures the student must each\n"
        "  describe). Each of those panels is one problem, even when they share a\n"
        "  single parent number. Use the label/name as the suffix, e.g. \"1-준서\",\n"
        "  \"1-수민\".\n"
        "- If problems have no visible numbering, count visually distinct questions\n"
        "  in reading order.\n"
        "- Include eligible items even if labeled \"Example\", \"Worked Example\",\n"
        "  \"Sample Problem\", or similar.\n"
        "- Ignore only page numbers, running headers, section titles with no\n"
        "  question attached, and pure decoration.\n"
        "\n"
        "Output ONLY a single-line JSON object, no markdown, no extra text, in this\n"
        "exact form:\n"
        "{\"problem_labels\": [\"<label>\", \"<label>\", ...], \"count\": <integer>}\n"
        "\n"
        "Rules for \"problem_labels\":\n"
        "- Use the visible label for each individual question. Combine the parent\n"
        "  number with the sub-part letter when both exist (e.g. \"1a\", \"1b\", \"2\",\n"
        "  \"3a\", \"3b\", \"3c\"). If unlabeled, use \"1\", \"2\", ... in reading order.\n"
        "- For independently answerable named cases inside one question, use the\n"
        "  visible case names as labels; include a visible parent label as a prefix\n"
        "  when useful for disambiguation.\n"
        "- One label per eligible text-answerable question. Never include the label\n"
        "  of an excluded visual, physical, or interactive task.\n"
        "- \"count\" must equal the length of \"problem_labels\"."
    )

    user_content: list[dict[str, Any]] = [{"type": "text", "text": instruction}]
    for path in image_paths or []:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": encode_image_to_data_url(path), "detail": "high"},
        })
    for url in image_urls or []:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "high"},
        })

    dprint(f"[Setup] Vision count model: {VISION_COUNT_MODEL} (reasoning_effort=none)")
    try:
        response = openai_client.chat.completions.create(
            model=VISION_COUNT_MODEL,
            messages=cast(Any, [
                {"role": "user", "content": user_content},
            ]),
            max_completion_tokens=4000,
            reasoning_effort="none",
        )
    except Exception as e:
        dprint(f"[Setup] ⚠️ Vision count failed: {e!s:.200s}")
        return None, []

    choice = response.choices[0]
    raw = (choice.message.content or "").strip()
    finish_reason = getattr(choice, "finish_reason", None)
    usage = getattr(response, "usage", None)
    dprint(
        f"[Setup] Vision count raw response: {raw!r} "
        f"(finish_reason={finish_reason}, usage={usage}, {time.time() - start:.2f}s)"
    )
    if not raw and finish_reason == "length":
        dprint(
            "[Setup] ⚠️ Empty content with finish_reason='length' — the model used "
            "all completion tokens (likely on hidden reasoning). Consider raising "
            "max_completion_tokens further or switching VISION_COUNT_MODEL to a "
            "non-reasoning vision model (e.g. 'gpt-4.1' or 'gpt-4o')."
        )

    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    labels: list[str] = []
    count: int | None = None
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            raw_labels = parsed.get("problem_labels", [])
            if isinstance(raw_labels, list):
                labels = [str(x).strip() for x in raw_labels if str(x).strip()]
            raw_count = parsed.get("count")
            if isinstance(raw_count, bool):
                pass
            elif isinstance(raw_count, int):
                count = raw_count
            elif isinstance(raw_count, str) and raw_count.strip().isdigit():
                count = int(raw_count.strip())
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    if labels:
        if count is not None and count != len(labels):
            dprint(
                f"[Setup] ℹ️ Label/count mismatch (labels={len(labels)}, count={count}); "
                "trusting the label list."
            )
        count = len(labels)

    if count is None:
        m = re.search(r"\d+", cleaned) or re.search(r"\d+", raw)
        if m:
            try:
                count = int(m.group(0))
            except ValueError:
                count = None

    if count is None:
        return None, labels

    if count < 1:
        return 0, []

    return count, labels

# ── Stance-2 opener JSON 파싱 ────────────────────────────────────
def parse_stance2_opener(raw: str) -> str:
    """Parse the JSON output of the stance-2 opener and return the user-facing line.

    Expected shape:
        {"correct_answer": "...", "wrong_answer": "...", "opener_text": "..."}

    Logs the (correct, wrong) pair for visibility and validates they differ.
    Falls back to the raw text if parsing fails so the loop can continue.
    """
    cleaned = (raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").strip()
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    try:
        parsed = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        dprint(
            f"[Stance 2 opener] ⚠️ JSON parse failed, falling back to raw text: "
            f"{raw!r:.300s}"
        )
        return raw

    if not isinstance(parsed, dict):
        dprint(f"[Stance 2 opener] ⚠️ JSON is not an object, falling back: {raw!r:.300s}")
        return raw

    correct = str(parsed.get("correct_answer", "")).strip()
    wrong = str(parsed.get("wrong_answer", "")).strip()
    text = str(parsed.get("opener_text", "")).strip()

    dprint(f"[Stance 2 opener] correct_answer={correct!r}, wrong_answer={wrong!r}")
    if correct and wrong and correct.lower() == wrong.lower():
        dprint(
            "[Stance 2 opener] ⚠️ Model returned wrong_answer == correct_answer — "
            "the validation step in the prompt was ignored."
        )

    if not text:
        dprint(f"[Stance 2 opener] ⚠️ opener_text is empty, falling back: {raw!r:.300s}")
        return raw

    return text


# ── GPT 답변 생성 ────────────────────────────────────────────────
def assess_latest_answer(
    user_input: str,
    image_paths: list[str] | None = None,
    image_urls: list[str] | None = None,
) -> str:
    """Classify the latest answer separately from dialogue generation."""
    descriptor = get_problem_descriptor()
    current_entries = PROBLEM_CONVERSATIONS.get(CURRENT_PROBLEM, [])
    history = "\n".join(
        f"{entry['type']}: {entry['description']}" for entry in current_entries
    ) or "(No prior dialogue.)"

    instruction = f"""You are an independent answer checker.

Evaluate ONLY {descriptor} in the attached image and the learner's latest
message. Re-solve the problem carefully before classifying the message. Pay
close attention to signs, subtraction order, coordinates, and arithmetic.

[Current-problem dialogue]
{history}

[Learner's latest message]
{user_input}

Return SOLVED when the latest message states the correct final answer for every
required part, even if it is short or corrects an earlier mistake.
Return INCORRECT only when the latest message makes a concrete, verifiably
wrong claim or gives a wrong answer.
Return UNCLEAR when it is partial, procedural, ambiguous, a question, or makes
no verifiable answer claim.

First identify exactly what the original problem in the image asks the learner
to find. That original requested result controls completion, not a narrower
question Isabella asked while guiding the learner. Set "contains_final_answer"
to true only when the latest message explicitly states the requested result.
Do not infer an unstated final answer merely because the learner wrote an
equation, substitution, transformation, or setup from which it could be
solved. Such work is UNCLEAR unless that form itself is what the original
problem requests. When the problem provides a template containing one unknown
parameter and asks the learner to identify the resulting expression, an
explicit correct value of that parameter is sufficient if it uniquely
determines the requested expression.

Judge mathematical meaning, not presentation. Accept harmless informal
formatting when the intended answer is unambiguous. For a requested ordered
pair or vector, accept two clearly stated comma-separated values without
requiring parentheses or angle brackets. Do not require units, a sentence, or
an explanation unless the problem explicitly requires one.

Show the verification inside a compact JSON object so the classification is
grounded in an explicit check. Set "contains_final_answer" to false for a
procedure, hint, question, partial step, or ambiguous statement. Never return
SOLVED unless "contains_final_answer" is true.

Output ONLY one JSON object:
{{"status":"SOLVED|INCORRECT|UNCLEAR","contains_final_answer":true|false,
"calculation":"brief private verification"}}
"""
    user_content: list[dict[str, Any]] = [{"type": "text", "text": instruction}]
    for path in image_paths or []:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": encode_image_to_data_url(path), "detail": "high"},
        })
    for url in image_urls or []:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "high"},
        })

    try:
        judge_kwargs: dict[str, Any] = {
            "model": ANSWER_JUDGE_MODEL,
            "messages": cast(Any, [
                {"role": "developer", "content": (
                    "Check mathematical correctness independently. Show the check "
                    "inside the requested JSON object and output only that JSON."
                )},
                {"role": "user", "content": user_content},
            ]),
        }
        if ANSWER_JUDGE_MODEL.startswith("gpt-5"):
            judge_kwargs.update(max_completion_tokens=500, reasoning_effort="none")
        else:
            judge_kwargs.update(temperature=0, max_tokens=300)
        response = openai_client.chat.completions.create(**cast(Any, judge_kwargs))
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        parsed = json.loads(raw)
        status = str(parsed.get("status", "UNCLEAR")).strip().upper()
        contains_final_answer = parsed.get("contains_final_answer") is True
        calculation = str(parsed.get("calculation", "")).strip()
        if status not in {"SOLVED", "INCORRECT", "UNCLEAR"}:
            status = "UNCLEAR"
        if not contains_final_answer and status != "UNCLEAR":
            status = "UNCLEAR"
        dprint(f"[Answer judge] {status}: {calculation}")
        return status
    except Exception as e:
        dprint(f"[Answer judge] Failed; using UNCLEAR: {e!s:.200s}")
        return "UNCLEAR"


def build_solved_reply(is_last_problem: bool) -> str:
    reply = "[EOP]\nThat's correct; you completed this problem."
    if is_last_problem:
        reply += "\n[EOF]"
    return reply


def strip_untrusted_control_markers(reply: str) -> str:
    """Prevent model-generated markers from controlling conversation state."""
    return reply.replace("[EOP]", "").replace("[EOF]", "").strip()


def reply_needs_shape_repair(reply: str) -> bool:
    visible_reply = reply.replace("[EOP]", "").replace("[EOF]", "").strip()
    word_count = len(re.findall(r"\b[\w'-]+\b", visible_reply))
    expected_question_marks = 0 if "[EOP]" in reply else 1
    return visible_reply.count("?") != expected_question_marks or word_count > 35


def generate_ai_response(
    dev_message: str,
    user_message: str,
    image_paths: list[str] | None = None,
    image_urls: list[str] | None = None,
) -> str:
    dprint("\nGPT가 답변을 생성하는 중...")
    start_llm = time.time()

    user_content: list[dict[str, Any]] = [{"type": "text", "text": user_message}]

    for path in image_paths or []:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": encode_image_to_data_url(path), "detail": "high"},
        })

    for url in image_urls or []:
        user_content.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "high"},
        })

    messages = cast(Any, [
        {"role": "developer", "content": dev_message},
        {"role": "user", "content": user_content},
    ])
    response = openai_client.chat.completions.create(
        # model="ft:gpt-4.1-2025-04-14:capstone1:friend-ai-test-1200:DhJIZ5M0",
        model="gpt-4.1",
        messages=messages,
        temperature=0.2,
        max_tokens=100
    )
    reply = response.choices[0].message.content or ""
    cleaned_reply = strip_untrusted_control_markers(reply)
    if cleaned_reply != reply.strip():
        dprint("[Control] Ignored completion marker emitted by dialogue model.")
    reply = cleaned_reply

    if reply_needs_shape_repair(reply):
        repair_messages = cast(Any, messages + [
            {"role": "assistant", "content": reply},
            {"role": "developer", "content": (
                "Rewrite the immediately preceding draft only. The problem is still "
                "active, so do not output [EOP] or [EOF]. Use no more than 35 visible "
                "words and exactly one question mark. Keep it "
                "grounded, use at most one small hint, reveal no final answer, and "
                "introduce no new facts or topic labels. If the learner's attempt "
                "is incorrect, begin exactly with \"That's incorrect.\" and do not "
                "praise the attempt. Output only the rewrite."
            )},
        ])
        response = openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=repair_messages,
            temperature=0,
            max_tokens=100,
        )
        reply = response.choices[0].message.content or reply
        reply = strip_untrusted_control_markers(reply)

    dprint(f"[Latency] 🤖 GPT 답변 생성: {time.time() - start_llm:.4f}초")
    return reply or "I may be missing one detail; which part of your reasoning should we check first?"

# ── 실행 ────────────────────────────────────────────────────────
def prompt_total_problems_manually(default: int = 1) -> int:
    while True:
        total_raw = input(
            f"How many problems are in the image? (default {default}): "
        ).strip()
        if not total_raw:
            return default
        try:
            parsed = int(total_raw)
            if parsed < 1:
                raise ValueError
            return parsed
        except ValueError:
            print("Please enter a positive integer.")


if __name__ == "__main__":
    dprint("Starting conversation with Isabella.")

    image_ref = input(
        "Enter an image path or URL (press Enter to skip): "
    ).strip().strip('"').strip("'")

    image_paths: list[str] = []
    image_urls: list[str] = []
    if image_ref:
        if image_ref.startswith("http://") or image_ref.startswith("https://"):
            image_urls.append(image_ref)
            dprint(f"Image URL will be attached to every reply: {image_ref}")
        else:
            if not os.path.isfile(image_ref):
                raise FileNotFoundError(f"Image file not found: {image_ref!r}")
            image_paths.append(image_ref)
            dprint(f"Image file will be attached to every reply: {image_ref}")
    else:
        dprint("Continuing without an image.")

    if image_paths or image_urls:
        detected, detected_labels = count_problems_in_image(
            image_paths=image_paths or None,
            image_urls=image_urls or None,
        )
        if detected is not None:
            if detected == 0:
                print(
                    "No text-answerable CLI problems were found in the image; "
                    "visual tasks such as sketching or graphing were excluded."
                )
                raise SystemExit(0)
            TOTAL_PROBLEMS = detected
            PROBLEM_LABELS = list(detected_labels)
            if detected_labels:
                dprint(
                    f"[Setup] Detected {TOTAL_PROBLEMS} problem(s): "
                    f"{', '.join(detected_labels)}"
                )
            else:
                dprint(f"[Setup] Detected {TOTAL_PROBLEMS} problem(s) in the image.")
        else:
            dprint("[Setup] Could not auto-detect problem count; falling back to manual entry.")
            TOTAL_PROBLEMS = prompt_total_problems_manually()
    else:
        TOTAL_PROBLEMS = prompt_total_problems_manually()
    dprint(f"Total problems set to {TOTAL_PROBLEMS}.")

    dprint("(Press Enter on an empty line to quit.)")
    last_opened_problem: int | None = None
    while True:
        if last_opened_problem != CURRENT_PROBLEM:
            opener_start = time.time()
            opener_dev, opener_user = build_prompt("", is_opener=True)

            dprint("\n" + "=" * 60)
            dprint(f"Isabella opens problem {CURRENT_PROBLEM}")
            dprint("=" * 60)
            dprint(opener_dev)
            dprint("=" * 60)
            dprint(opener_user)
            if image_paths or image_urls:
                dprint(f"Attached image: {len(image_paths)} file(s), {len(image_urls)} URL(s)")
            dprint("=" * 60)

            opener_raw = generate_ai_response(
                opener_dev,
                opener_user,
                image_paths=image_paths or None,
                image_urls=image_urls or None,
            )

            if get_stance_for_problem(CURRENT_PROBLEM) == 2:
                opener_reply = parse_stance2_opener(opener_raw)
            else:
                opener_reply = opener_raw

            add_to_session_memory("ai", opener_reply)
            increment_turn_count(CURRENT_PROBLEM)
            last_opened_problem = CURRENT_PROBLEM

            print_isabella_reply(opener_reply)
            dprint(f"🎯 Opener latency: {time.time() - opener_start:.4f}s")

        raw_input_str = input("You: ").strip()
        if not raw_input_str:
            dprint("Ending conversation.")
            break

        user_input = raw_input_str

        start_total = time.time()
        answer_status = assess_latest_answer(
            user_input,
            image_paths=image_paths or None,
            image_urls=image_urls or None,
        )
        if answer_status == "SOLVED":
            ai_reply = build_solved_reply(CURRENT_PROBLEM >= TOTAL_PROBLEMS)
        else:
            dev_message, user_message = build_prompt(
                user_input,
                answer_status=answer_status,
            )

            dprint("\n" + "=" * 60)
            dprint("📝 Developer message")
            dprint("=" * 60)
            dprint(dev_message)
            dprint("=" * 60)
            dprint("📝 User message")
            dprint("=" * 60)
            dprint(user_message)
            if image_paths or image_urls:
                dprint(f"🖼️  첨부 이미지: {len(image_paths)} 파일, {len(image_urls)} URL")
            dprint("=" * 60)

            ai_reply = generate_ai_response(
                dev_message,
                user_message,
                image_paths=image_paths or None,
                image_urls=image_urls or None,
            )

        ai_reply_for_memory = ai_reply.replace("[EOP]", "").replace("[EOF]", "").strip()

        add_to_session_memory("user", user_input)
        if ai_reply_for_memory:
            add_to_session_memory("ai", ai_reply_for_memory)

        increment_turn_count(CURRENT_PROBLEM)

        problem_just_solved = answer_status == "SOLVED"
        if problem_just_solved:
            record_problem_thought_async(
                problem_num=CURRENT_PROBLEM,
                total_problems=TOTAL_PROBLEMS,
                image_paths=image_paths or None,
                image_urls=image_urls or None,
            )
            CURRENT_PROBLEM += 1
            if CURRENT_PROBLEM > TOTAL_PROBLEMS:
                dprint(f"✅ Problem {CURRENT_PROBLEM - 1} complete! That was the last problem.")
            else:
                dprint(f"✅ Problem {CURRENT_PROBLEM - 1} complete! Moving on to problem {CURRENT_PROBLEM}.")

        all_done = problem_just_solved and CURRENT_PROBLEM > TOTAL_PROBLEMS
        if all_done:
            dprint("🎉 All problems finished!")

        print_isabella_reply(ai_reply)
        dprint(f"🎯 총 체감 레이턴시(Total Latency): {time.time() - start_total:.4f}초")

        if all_done:
            break
