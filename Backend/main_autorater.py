import os
import re
import json
import ast
import base64
import logging
import warnings
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

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

BACKEND_DIR = Path(__file__).resolve().parent
EXAMPLES_DIR = BACKEND_DIR / "assets" / "Examples"
EXAMPLE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def _natural_sort_key(path: Path) -> list[int | str]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", path.name)
    ]


def get_first_example_image_path(examples_dir: Path = EXAMPLES_DIR) -> str | None:
    if not examples_dir.is_dir():
        return None

    image_paths = sorted(
        (
            path for path in examples_dir.iterdir()
            if path.is_file() and path.suffix.lower() in EXAMPLE_IMAGE_EXTENSIONS
        ),
        key=_natural_sort_key,
    )
    return str(image_paths[0]) if image_paths else None

# ── Teaching mode display ────────────────────────────────────────
# New explicit debug switch: when enabled, Isabella's visible output includes
# the teaching mode used for that reply.
DEBUG_SHOW_TEACHING_MODE: bool = False


def dprint(*args: Any, **kwargs: Any) -> None:
    """Compatibility no-op for removed verbose diagnostics."""
    return None


def format_teaching_mode(strategy: str | None = None) -> str:
    raw_strategy = strategy or globals().get("PROBLEM_STRATEGY", {}).get(
        globals().get("CURRENT_PROBLEM", 1),
        "socratic",
    )
    labels = {
        "socratic": "Socratic",
        "worked_example_fading": "Worked-example fading",
        "protege_effect": "Protege effect",
    }
    return labels.get(str(raw_strategy), str(raw_strategy).replace("_", " ").title())


def print_isabella_reply(reply: str, strategy: str | None = None) -> None:
    """Print Isabella's reply, optionally showing the teaching mode."""
    display_reply = reply.replace("[EOP]", "").replace("[EOF]", "").strip()
    if display_reply:
        mode_text = (
            f" [mode: {format_teaching_mode(strategy)}]"
            if DEBUG_SHOW_TEACHING_MODE
            else ""
        )
        print(f"Isabella{mode_text}: {display_reply}")


def _configure_quiet_libs() -> None:
    """Silence Hugging Face / transformers startup noise."""
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

VISION_COUNT_MODEL = os.getenv("VISION_COUNT_MODEL", "gpt-4.1")
ANSWER_JUDGE_MODEL = os.getenv("ANSWER_JUDGE_MODEL", VISION_COUNT_MODEL)

# Probability the coin flip lands on stance 2 (plausibly mistaken opener).
# 0.5 = unbiased; 1.0 = always wrong; 0.0 = always helpful.
STANCE_2_PROBABILITY = 0.0

SOCRATIC_POLICY = """
================================================================
[SOCRATIC RESPONSE POLICY - HIGHEST PRIORITY]
================================================================
Follow this policy instead of any conflicting style instruction.

Act as a calm, friendly learning buddy for an elementary or early
middle-school learner. Help the learner think and self-correct; do not act as
an answer bot.

Use Socratic discovery: ask a focused question, let the learner answer, then
ask why, what it represents, how to check it, or what follows. The learner
should state the missing connection whenever possible; do not hand it to them.

For every educational reply:
- Write 16-28 words when practical and never more than 35 words.
- Use one sentence when practical; two short sentences are acceptable.
- Ask exactly ONE main educational question and use exactly ONE question mark.
  Do not ask a multi-part question joined by "and" or "or", and do not add a
  second implied question after a dash, comma, or semicolon.
  Never use phrases like "and how", "and what", "or how", or "or what" in the
  same question.
- Give at most ONE small, useful hint or check. Never give a full procedure,
  a list of steps, the complete setup, or the final answer.
- If the learner asks for a formula, method, rule, or procedure, do not provide
  the named formula, symbolic template, or worked setup immediately. Ask what
  quantities they already know, what changes each period/step, or what the
  expression should represent. Reveal formula pieces only after the learner has
  identified the need for that piece.
- If the current item asks the learner to evaluate, calculate, compute, find an
  amount, or find a value/result, a substituted expression or model expression
  is only an intermediate step. Ask what numerical amount/value it gives unless
  the original item explicitly asks for an expression, equation, model, setup,
  or formula. Do not merely ask what the expression represents.
- For direct function-evaluation tasks, if the learner only writes the defining
  formula with the input substituted, ask what value that expression simplifies
  to or is approximately equal to. Do not ask only what it "represents."
- Keep the current problem's exact concept and operation. Use only details
  supported by the image, the learner's message, or the dialogue history.
- Do not invent facts, examples, context, or topic labels.
- If the learner gives an attempt, respond to their visible reasoning first.
  Ask about the step, count, substitution, or assumption that led to it before
  offering a corrective hint.
- If the learner's attempt is incorrect, do not announce "That's incorrect" and
  do not thank, praise, or validate the answer. Do not immediately give the
  procedure, computation, or correction. If the learner only gives a final
  answer, ask why they thought that or how they got that exact answer; do not
  ask them to check, calculate, multiply, simplify, solve, or work step by step
  yet. For this bare final-answer case, prefer this diagnostic shape and
  nothing else: Why did you think it was <their answer>?
  Mention only the learner's answer, not the formula, expression,
  operation, or other numbers from the problem. Do not infer their reasoning
  from Isabella's previous question; the learner must state their own path. If their reasoning is already
  visible, briefly name that reasoning as a statement, not a question, then ask
  one targeted check that helps them inspect their own work before comparing it
  to the rule. Prefer observation questions such as count, chosen value, sign,
  or operation; avoid "should" until the learner has noticed what they actually
  did. Do not use the word "should" in the first response to visible incorrect
  reasoning. If they show a concrete arithmetic expression, ask only about an
  observable feature of that expression first; do not mention the rule or the
  correct expected feature yet. For repeated multiplication, use only this
  two-sentence shape: You wrote <their expression>. How many factors of <base>
  did you write? Do not mention the exponent, substitution value, or correct
  count in that same reply.
- If the learner corrects you, accept it warmly without defending the mistake,
  then ask them to explain or restate the corrected idea unless their
  correction completes the current problem.
- If the learner gives a correct or useful intermediate answer, do not begin
  with "Yes", "That's right", "Correct", or "You're right." Do not restate the
  connection as a teaching sentence. Instead, ask why it makes sense, what it
  represents, how they could check it, or what follows from it. Start directly
  with the question when possible; do not begin by paraphrasing with "You said"
  or "You noticed" unless the learner's wording is ambiguous. Ask about only
  one conceptual link, not both interpretation and the next calculation. If a
  quantity has multiple parts, ask about one part at a time. If the learner
  gives only a useful number or expression, ask what it represents before
  introducing a new operation with it. Use shapes like "What does <their
  number> represent here?" or "What does <their expression> represent here?"
  Do not ask how to use that number or expression in the same reply.
  For rates and percentages, ask what base quantity the rate applies to or what
  one-period change it creates before asking about a multiplier or formula. Use
  shapes like "What amount does that rate apply to?" or "How much is <rate> of
  <base> for one period?" Do not say "multiplying by <rate>" yet.
  If the learner answers a concrete quantity you asked for, ask for the next
  missing quantity it unlocks rather than confirming it or asking how they got
  it, unless their reasoning seems suspect.
- Reserve direct confirmation for final solved replies or when the learner
  explicitly asks whether a step is correct. Even then, keep it very short and
  ask a reasoning question unless the current problem is complete.
- If the learner says they have seen a formula, method, or rule before, do not
  ask them to plug all values into it at once. Ask them to identify one
  component or one relationship at a time.
- If the learner only says they understand, ask them to restate one idea
  without guessing or naming the subject.
- Use simple, natural English. Never say "Nice effort", "Good try", "Thanks
  for your answer", "Try...", or similar praise/coaching after an incorrect
  attempt. Avoid "Yes, ...", "That's right, ...", and "Correct, ..." for
  intermediate steps. Avoid overpraise, silliness, excessive excitement,
  exclamation marks, and formal teacher language.

For an opener, make one grounded observation about the visible problem and ask
one concrete question that invites the learner's first reasoning step. Do not
state or imply an answer. For word problems, start from a concrete given value
or prerequisite quantity before asking about an abstract method, formula, or
definition.

Before sending, silently check: no answer leak, one hint at most, grounded
wording, and no more than 35 words. Use exactly one question mark while the
problem is active; use zero question marks after the problem is complete.
================================================================
"""

WORKED_EXAMPLE_FADING_POLICY = """
================================================================
[WORKED-EXAMPLE FADING RESPONSE POLICY - HIGHEST PRIORITY]
================================================================
Follow this policy instead of any conflicting style instruction.

Act as a calm, friendly learning buddy for an elementary or early
middle-school learner. The previous subproblem used the same core idea as the
current one. Use that solved case as a model, then fade support so the learner
adapts the structure themselves.

For every educational reply:
- Write 18-35 words when practical and never more than 45 words.
- Use one or two short sentences.
- Ask exactly ONE main educational question and use exactly ONE question mark.
- Briefly anchor to the previous solved case when useful, then ask what changes
  in the current case. Do not reteach the whole idea from scratch.
- Keep the anchor short. Do not both restate the learner's latest answer and
  explain the previous case in the same reply.
- You may give one modeled piece from the previous case, but leave the current
  case's changed piece for the learner. Never give the full current expression,
  full setup, or final numeric answer.
- Because this is fading, it is okay to ask for two tightly linked changed
  quantities in one question when both are needed to adapt the prior example.
- If the learner identifies one changed input, parameter, count, condition, or
  case feature, ask for the next linked changed quantity or relationship needed
  to adapt the previous solution. Use a concise shape like "What changes in the
  setup for this case?"
- If the learner gives the changed values, ask them to write the adapted
  expression. If they give the expression and the current item asks for an
  amount/value/result, ask what numerical amount/value it gives. If the current
  item asks for an expression/model, ask one brief meaning/check question
  unless the answer judge already marked it solved.
- If the learner asks for a formula, method, rule, or procedure, point back to
  the previous structure and ask which part changes for the current case. Do
  not provide the symbolic template immediately.
- If the learner is wrong, do not announce "That's incorrect." Ask them to
  compare the current case with the previous solved case and identify the one
  value or count that changed.
- Keep the current problem's exact concept and operation. Use only details
  supported by the image, the learner's message, or the dialogue history.
- Use simple, natural English. Avoid overpraise, exclamation marks, and formal
  teacher language. Do not start with "Great", "Good", "Yes", "That's right",
  "Right", "Nice", "Thanks", or "Correct" for intermediate steps.

For an opener, remind the learner they already solved the previous case using
the same structure, then ask one concrete adaptation question about what
changes in the current case. Do not reveal the current expression or answer.

Before sending, silently check: prior case used only as a model, current case
not solved for them, one main question, grounded wording, and no more than 45
words. Use exactly one question mark while the problem is active; use zero
question marks after the problem is complete.
================================================================
"""

PROTEGE_EFFECT_POLICY = """
================================================================
[PROTEGE EFFECT RESPONSE POLICY - HIGHEST PRIORITY]
================================================================
Follow this policy instead of any conflicting style instruction.

Act as Isabella, a calm learning buddy who is temporarily becoming the learner.
The learner just completed a related earlier subproblem. Use the protege effect:
invite the learner to teach or correct Isabella so the learner explains the
same idea in the current case.

Use a two-phase Protege flow:
1. Opening correction phase: Isabella starts with a plausible wrong reasoning
   chain about the current case, then asks the learner to explain why it is
   wrong or how to fix it.
2. Explanation phase: after the learner corrects the wrong reasoning, Isabella
   stops introducing new unrelated mistakes and continues like a normal
   conversation where the learner teaches the idea, one step at a time.

For every educational reply:
- Write 18-45 words when practical and never more than 55 words.
- Use one or two short sentences.
- Ask exactly ONE main educational question and use exactly ONE question mark.
- Briefly anchor to the previous solved case only when useful.
- In the opening correction phase, present one plausible wrong reasoning chain,
  not just a wrong value. The reasoning should sound like Isabella copied part
  of the previous solved case too mechanically.
- The wrong reasoning must target the changed parameter, count, operation,
  representation, or relationship.
- The wrong reasoning must actually be wrong for the current case. Do not
  present a correct method as a vague "will this work?" uncertainty.
- Use one question only. Prefer the shape: "I think <wrong reasoning>. Can you
  explain why that reasoning is wrong?"
- Ask the learner to explain why Isabella's reasoning is wrong or teach how to
  fix it.
- Do not give the full current setup, expression, formula, or final answer.
- Do not make a misconception so large or silly that it changes the problem.
  It should be a realistic near-miss based on the previous solved case.
- After the learner corrects the misconception, do not immediately invent a new
  wrong guess unless their correction is missing the key idea. Ask one natural
  follow-up that lets them explain the reason, state the adapted value/count,
  or write the expression.
- If the learner says "no", "not exactly", "that changes", or otherwise rejects
  Isabella's misconception, do not ask whether the same wrong idea is correct.
  Ask what the corrected value/count/relationship should be or why it changes.
- If the learner already states the corrected value/count/relationship, do not
  ask for it again and do not introduce a second new misconception. Ask why
  that correction is true or how it changes the next setup piece.
- After a correction, do not ask whether another value "stays the same", "stays
  like before", or "is still" the previous case's value. Ask what the changed
  value becomes instead.
- Prefer explanation prompts after a correction: "Why does that change?",
  "How did you decide that?", "What does that make the new value?", or "How
  would you write the expression now?"
- If the learner gives the expression and the current item asks for an
  amount/value/result, ask what numerical amount/value it gives. If the current
  item asks for an expression/model, ask one brief meaning/check question
  unless the answer judge already marked it solved.
- If the learner is wrong, stay in learner mode and ask them to compare with
  the previous case or explain the changed piece again. Do not announce
  "That's incorrect."
- Keep the current problem's exact concept and operation. Use only details
  supported by the image, the learner's message, or the dialogue history.
- Use simple, natural English. Avoid overpraise, exclamation marks, and formal
  teacher language. Do not start with "Great", "Good", "Yes", "That's right",
  "Right", "Nice", or "Correct" for intermediate steps.

For an opener, switch roles briefly: say Isabella is the student for this one,
offer one plausible wrong reasoning chain about the current case, and ask the
learner to explain why that reasoning is wrong or how to fix it. Do not reveal
the current expression or answer.

Before sending, silently check: Isabella is genuinely inviting the learner to
teach, the near-miss includes reasoning, the current case is not solved for
them, one main question, grounded wording, and no more than 55 words. Use
exactly one question mark while the problem is active; use zero question marks
after the problem is complete.
================================================================
"""

# Backward-compatible name for legacy prompt code. The active prompt chooses a
# strategy-specific policy through get_current_teaching_policy().
LEARNING_FRIEND_POLICY = SOCRATIC_POLICY

MATH_RENDERING_INSTRUCTION = """
[Math display]
When Isabella includes symbolic math or formulas, write them as renderable
Markdown math: use `$...$` for inline math and `$$...$$` for a displayed
formula. Do not put formulas in backticks.
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
PROBLEM_STRATEGY: dict[int, str] = {}
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
    PROBLEM_STRATEGY.clear()


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
        return f'the case or subproblem labeled "{label}" in the image (item {CURRENT_PROBLEM} of {TOTAL_PROBLEMS})'
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


def get_previous_problem_context(max_entries: int = 8) -> str:
    """Recent dialogue from the immediately previous subproblem, if any."""
    previous_entries = PROBLEM_CONVERSATIONS.get(CURRENT_PROBLEM - 1, [])
    if not previous_entries:
        return ""

    type_labels = {
        "user": "Learner",
        "ai": "Isabella",
        "action": "Action",
        "chat": "Summary",
    }
    lines = [
        f"{type_labels.get(entry['type'], entry['type'])}: {entry['description']}"
        for entry in previous_entries[-max_entries:]
    ]
    return "\n".join(lines)


def get_current_teaching_strategy() -> str:
    """Return the cached teaching strategy for the current problem."""
    if CURRENT_PROBLEM <= 1:
        return "socratic"
    return PROBLEM_STRATEGY.get(CURRENT_PROBLEM, "socratic")


def get_current_teaching_policy() -> str:
    if get_current_teaching_strategy() == "protege_effect":
        return PROTEGE_EFFECT_POLICY
    if get_current_teaching_strategy() == "worked_example_fading":
        return WORKED_EXAMPLE_FADING_POLICY
    return SOCRATIC_POLICY


def choose_strategy_from_relation(problem_num: int, relation: str) -> str:
    """Apply the strategy sequence once the idea relationship is known."""
    if problem_num <= 1 or relation != "same_core_idea":
        return "socratic"

    previous_strategy = PROBLEM_STRATEGY.get(problem_num - 1, "socratic")
    if previous_strategy == "socratic":
        return "worked_example_fading"
    if previous_strategy == "worked_example_fading":
        return "protege_effect"
    if previous_strategy == "protege_effect":
        return random.choice(["worked_example_fading", "protege_effect"])
    return "worked_example_fading"


def determine_teaching_strategy_for_problem(
    problem_num: int,
    image_paths: list[str] | None = None,
    image_urls: list[str] | None = None,
) -> str:
    """Choose Socratic, worked-example fading, or protege effect."""
    if problem_num <= 1:
        PROBLEM_STRATEGY[problem_num] = "socratic"
        return "socratic"
    if problem_num in PROBLEM_STRATEGY:
        return PROBLEM_STRATEGY[problem_num]

    previous_label = PROBLEM_LABELS[problem_num - 2] if problem_num - 2 < len(PROBLEM_LABELS) else f"problem {problem_num - 1}"
    current_label = PROBLEM_LABELS[problem_num - 1] if problem_num - 1 < len(PROBLEM_LABELS) else f"problem {problem_num}"
    manifest = get_problem_manifest() or "(No detected labels.)"

    instruction = f"""Decide whether the CURRENT subproblem uses the same core idea as
the immediately previous subproblem.

Rules:
- Return "same_core_idea" only when the current subproblem can be solved by
  adapting the same core idea/procedure as the previous subproblem, with changed
  values, cases, labels, counts, intervals, or conditions.
- Return "new_idea" when the current subproblem introduces a new mathematical
  feature, representation, or operation property, even if it appears in the same
  parent exercise. Examples include changing from whole numbers to negative
  numbers, fractions, decimals, radicals, irrational values, variables, absolute
  values, roots, reciprocals, domain restrictions, inverse operations, sign
  cases, or a new diagram/table/representation.
- For exponent problems, changing from a positive integer exponent to a
  negative, fractional, radical, irrational, or variable exponent is
  "new_idea". Merely changing one ordinary numeric value while using the same
  exponent rule is "same_core_idea".
- For formula/case-list problems, changing only a parameter such as a rate,
  count, interval, method name, or case condition while the same formula
  structure applies is "same_core_idea".
- Return "new_idea" when unsure.
- Do not decide from labels alone. Inspect the actual math in the image for the
  previous and current subproblems.

[Problem manifest]
{manifest}

[Previous subproblem]
{previous_label}

[Current subproblem]
{current_label}

Output ONLY JSON:
{{"relation":"same_core_idea|new_idea","reason":"short reason"}}"""

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

    relation = "new_idea"
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=cast(Any, [
                {"role": "developer", "content": "Classify the subproblem relationship and output only valid JSON."},
                {"role": "user", "content": user_content},
            ]),
            temperature=0,
            max_tokens=120,
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").strip()
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        parsed = json.loads(raw)
        parsed_relation = str(parsed.get("relation", "")).strip()
        if parsed_relation in {"same_core_idea", "new_idea"}:
            relation = parsed_relation
        strategy = choose_strategy_from_relation(problem_num, relation)
        dprint(
            f"[Strategy] Problem {problem_num}: {strategy} via {relation} "
            f"({str(parsed.get('reason', '')).strip()})"
        )
    except Exception as e:
        dprint(f"[Strategy] Failed; defaulting problem {problem_num} to Socratic: {e!s:.200s}")
        strategy = "socratic"

    PROBLEM_STRATEGY[problem_num] = strategy
    return strategy


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
    teaching_strategy = get_current_teaching_strategy()
    teaching_policy = get_current_teaching_policy()
    previous_context = get_previous_problem_context()
    previous_block = (
        f"\n[Previous solved subproblem - use only as a model]\n{previous_context}\n"
        if teaching_strategy == "worked_example_fading" and previous_context
        else ""
    )

    if is_opener:
        if teaching_strategy == "protege_effect":
            opening_style = (
                "Switch roles briefly: Isabella is the student for this one. "
            "Anchor to the previous solved subproblem, offer one plausible "
            "wrong reasoning chain about the current case, and ask the learner "
            "to explain why that reasoning is wrong or how to fix it. Do not "
            "reveal the current expression or answer."
            )
        elif teaching_strategy == "worked_example_fading":
            opening_style = (
                "Start by briefly reminding the learner that the previous subproblem "
                "used the same structure, then ask what changes for this current case. "
                "Do not reveal the current expression or answer."
            )
        else:
            opening_style = (
                "Start with a brief, natural meta statement that welcomes the learner "
                "into solving this one together, then move into the math. Vary this "
                "phrasing across problems; do not reuse a fixed line. Keep it casual "
                "and peer-like. After that, make one grounded observation from the "
                "image and ask one concrete first-step question. Do not reveal the answer."
            )
        dev_message = f"""
Only speak English. You are Isabella, a calm learning buddy.

[Current problem]
Focus only on {descriptor} in the attached image. This is a new conversation
about that problem. Do not evaluate earlier problems and do not solve it.

[Teaching strategy]
{teaching_strategy}
{previous_block}
{teaching_policy}

{MATH_RENDERING_INSTRUCTION}

[Control markers]
Do not output [EOP] or [EOF] in an opener.

[Opening style]
{opening_style}
"""
        user_message = f"""[Current-problem dialogue]
{history}
{previous_block}

Open the conversation about {descriptor}. Include the brief collaborative
opening style from the developer message, then use one grounded observation and
exactly one question that invites the learner's first reasoning step.
"""
        return dev_message, user_message

    if teaching_strategy == "protege_effect":
        answer_assessment_rules = """- INCORRECT: stay in learner mode. Do not say "That's incorrect"; ask the
  learner to teach or correct the changed value, count, operation, or
  relationship by comparing it with the previous solved case.
- UNCLEAR: do not call it correct or incorrect. If it is a useful correction or
  explanation, do not introduce a brand-new misconception; ask the learner to
  explain the reason, state the next adapted piece, or write the current
  expression. If the learner rejects Isabella's misconception, do not ask
  whether the same wrong idea is correct; ask what the corrected
  value/count/relationship should be or why it changes. If the learner already
  stated the corrected value/count/relationship, ask why that correction is true
  or how it changes the next setup piece. After a correction, do not ask whether
  another value stays the same or is still the previous case's value; ask what
  it becomes instead. If the learner gives an expression for an item that asks
  for an amount/value/result, ask what numerical amount/value it gives. If the
  learner asks for a formula, method, rule, or procedure, ask them to teach
  which part of the previous structure changes here.
- SOLVED is handled by the program before this prompt is used."""
    elif teaching_strategy == "worked_example_fading":
        answer_assessment_rules = """- INCORRECT: do not say "That's incorrect"; ask the learner to compare the
  current case with the previous solved case and identify the one value, count,
  or relationship that changed.
- UNCLEAR: do not call it correct or incorrect. If it is a useful intermediate
  answer, ask for the next adapted piece, the current expression, or the
  evaluated value depending on what the item asks for. If the learner gives an
  expression for an item that asks for an amount/value/result, ask what
  numerical amount/value it gives. For direct function evaluation, ask what value the substituted
  expression simplifies to or is approximately equal to. If it asks for a
  formula, method, rule, or procedure, point back to the previous structure and
  ask which part changes.
- SOLVED is handled by the program before this prompt is used."""
    else:
        answer_assessment_rules = """- INCORRECT: do not say "That's incorrect"; ask one Socratic diagnostic or
  observation question. If the learner gave only an answer, ask why they
  thought that or how they got that answer. Prefer "Why did you think it was
  <their answer>?" Do not infer reasoning from Isabella's previous question,
  and do not ask them to check, calculate, multiply, simplify, solve, or work
  step by step until they reveal their reasoning.
  If the learner showed reasoning, ask what they notice about that reasoning
  before asking what they should have done.
- UNCLEAR: do not call it correct or incorrect. If it looks like a useful
  intermediate answer, do not confirm or explain it; ask why it works, what it
  represents, how to check it, or what follows. Otherwise ask one useful next
  question. If it asks for a formula, method, rule, or procedure, do not state
  the formula or procedure; ask one question about the known quantities,
  repeated change, or meaning of the expression. If the learner gives an
  expression for an item that asks for an amount/value/result, ask what
  numerical amount/value it gives. For direct function evaluation, ask what value the substituted
  expression simplifies to or is approximately equal to.
- SOLVED is handled by the program before this prompt is used."""

    dev_message = f"""
Only speak English. You are Isabella, a calm learning buddy.

[Current problem]
Focus only on {descriptor} in the attached image and the current-problem
dialogue. Ignore unrelated details from other problems.

[Teaching strategy]
{teaching_strategy}
{previous_block}

[Authoritative answer assessment]
An independent correctness judge classified the learner's latest message as
{answer_status}. Treat this classification as authoritative:
{answer_assessment_rules}

[Control markers]
The program has already determined that this problem is still active. Never
output [EOP] or [EOF]. A correct intermediate step is not completion; respond
to it and ask for the next reasoning step.

[Avoid circular rewriting]
If the learner's latest message looks like an exact final expression but its
notation is ambiguous, ask one short clarification about what they mean instead
of asking them to transform it again. Do not require a different equivalent
form unless the original problem explicitly asks for that representation.

{MATH_RENDERING_INSTRUCTION}

{teaching_policy}
"""
    user_message = f"""[Current-problem dialogue]
{history}
{previous_block}

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
        "  This includes comma-separated or series lists after wording such as\n"
        "  \"for\", \"if\", \"when\", \"under\", \"using\", \"by\", or \"compared across\",\n"
        "  when each listed name changes the answer to be calculated or verified.\n"
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

    dprint(f"[Setup] Vision count model: {VISION_COUNT_MODEL}")
    try:
        count_kwargs: dict[str, Any] = {
            "model": VISION_COUNT_MODEL,
            "messages": cast(Any, [
                {"role": "user", "content": user_content},
            ]),
        }
        if VISION_COUNT_MODEL.startswith("gpt-5"):
            count_kwargs.update(max_completion_tokens=4000, reasoning_effort="none")
        else:
            count_kwargs.update(max_tokens=1000, temperature=0)
        response = openai_client.chat.completions.create(**cast(Any, count_kwargs))
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
def _matches_example_one_part_b_answer(
    user_input: str,
    current_entries: list[dict[str, str]],
) -> bool:
    """Deprecated targeted shortcut; the generic judge now handles this."""
    del user_input, current_entries
    return False


def _looks_like_unevaluated_special_power(user_input: str) -> bool:
    """Detect power expressions that are usually intermediate for evaluation."""
    compact = user_input.lower().replace("−", "-").replace("–", "-")
    compact = re.sub(r"\s+", "", compact)
    compact = compact.strip(".")

    if not compact or any(token in compact for token in ("about", "approx")):
        return False
    if any(token in compact for token in ("root", "√", "∛")):
        return True

    def special_exponent(exp: str) -> bool:
        exp = exp.strip("()")
        if re.fullmatch(r"\d+", exp):
            return False
        return (
            exp.startswith("-")
            or "/" in exp
            or "pi" in exp
            or "π" in exp
            or "sqrt" in exp
        )

    simple_power = re.fullmatch(
        r"\(?([0-9]+(?:\.[0-9]+)?)\)?(?:\^|\*\*)\(?(.+?)\)?",
        compact,
    )
    if simple_power and special_exponent(simple_power.group(2)):
        return True

    parenthesized_power = re.fullmatch(
        r"\(.+?\)(?:\^|\*\*)\(?(.+?)\)?",
        compact,
    )
    if parenthesized_power and special_exponent(parenthesized_power.group(1)):
        return True

    reciprocal_power = re.fullmatch(
        r"1/\(?([0-9]+(?:\.[0-9]+)?)(?:\^|\*\*)\(?(.+?)\)?\)?",
        compact,
    )
    if reciprocal_power and special_exponent(reciprocal_power.group(2)):
        return True

    return False


def _safe_eval_numeric_expr(expr: str) -> float | None:
    """Evaluate a numeric arithmetic expression without exposing eval()."""
    normalized = expr.replace("^", "**").replace("×", "*").replace(",", "")
    normalized = normalized.strip()
    if not normalized or not re.fullmatch(r"[0-9eE+\-*/().\s]+", normalized):
        return None

    try:
        tree = ast.parse(normalized, mode="eval")
    except SyntaxError:
        return None

    def eval_node(node: ast.AST) -> float:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.UnaryOp):
            value = eval_node(node.operand)
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.USub):
                return -value
        if isinstance(node, ast.BinOp):
            left = eval_node(node.left)
            right = eval_node(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left ** right
        raise ValueError("unsupported expression")

    try:
        value = eval_node(tree)
    except (ArithmeticError, OverflowError, ValueError):
        return None
    if not math.isfinite(value):
        return None
    return value


def get_numeric_equation_check(user_input: str) -> str:
    """Summarize any self-contained numeric equation in the learner message."""
    summaries: list[str] = []
    for expr, stated_raw, evaluated, stated in get_self_consistent_numeric_equations(user_input, include_mismatches=True):
        difference = abs(evaluated - stated)
        tolerance = max(1e-6, abs(evaluated) * 1e-4)
        verdict = "matches" if difference <= tolerance else "does not match"
        summaries.append(
            f'- Learner wrote "{expr} = {stated_raw}". Safe arithmetic gives '
            f"{evaluated:.10g}; the stated value {verdict} within tolerance."
        )
    if not summaries:
        return ""
    return "[Detected numeric equation check]\n" + "\n".join(summaries)


def get_self_consistent_numeric_equations(
    user_input: str,
    include_mismatches: bool = False,
) -> list[tuple[str, str, float, float]]:
    """Return numeric equations whose typed expression matches the stated value."""
    matches = re.finditer(
        r"([0-9][0-9eE+\-*/^().,\s×]*?)\s*=\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
        user_input,
    )
    equations: list[tuple[str, str, float, float]] = []
    for match in matches:
        expr = match.group(1).strip()
        stated_raw = match.group(2).strip()
        evaluated = _safe_eval_numeric_expr(expr)
        stated = _safe_eval_numeric_expr(stated_raw)
        if evaluated is None or stated is None:
            continue
        difference = abs(evaluated - stated)
        tolerance = max(1e-6, abs(evaluated) * 1e-4)
        if include_mismatches or difference <= tolerance:
            equations.append((expr, stated_raw, evaluated, stated))
    return equations


def normalize_number_commas(text: str) -> str:
    """Remove thousands separators inside numeric literals."""
    return re.sub(r"(?<=\d),(?=\d{3}(?:\D|$))", "", text)


def assess_latest_answer(
    user_input: str,
    image_paths: list[str] | None = None,
    image_urls: list[str] | None = None,
    _allow_equation_fallback: bool = True,
) -> str:
    """Classify the latest answer separately from dialogue generation."""
    descriptor = get_problem_descriptor()
    manifest = get_problem_manifest() or "(No detected labels.)"
    current_label = get_current_label() or f"item {CURRENT_PROBLEM}"
    normalized_user_input = normalize_number_commas(user_input)
    numeric_equation_check = get_numeric_equation_check(user_input)
    numeric_equation_block = f"\n{numeric_equation_check}\n" if numeric_equation_check else ""
    current_entries = PROBLEM_CONVERSATIONS.get(CURRENT_PROBLEM, [])
    history = "\n".join(
        f"{entry['type']}: {entry['description']}" for entry in current_entries
    ) or "(No prior dialogue.)"
    if _matches_example_one_part_b_answer(user_input, current_entries):
        dprint("[Answer judge] SOLVED: matched Example 1(b) exact-form shortcut.")
        return "SOLVED"
    if _looks_like_unevaluated_special_power(user_input):
        dprint("[Answer judge] UNCLEAR: unevaluated special power expression.")
        return "UNCLEAR"

    instruction = f"""You are an independent answer checker.

Evaluate ONLY {descriptor} in the attached image and the learner's latest
message. Re-solve the problem carefully before classifying the message. Pay
close attention to signs, subtraction order, coordinates, and arithmetic.

[Detected problem/case manifest]
{manifest}

[Current item label]
{current_label}

If {descriptor} is one named sub-part, case, condition, scenario, method, or
category inside a larger parent question, evaluate completion for ONLY that
current named item. Do not require answers for sibling cases from the same
parent question. For example, if the current item is one listed case, a correct
answer for that case alone is SOLVED even though other listed cases remain.
If the current item label is a bare case name such as "annually",
"quarterly", "(b)", or "method 2", locate that named case inside the parent
problem in the image before judging. The absence of the parent number in the
label does not mean this is a standalone problem.

[Current-problem dialogue]
{history}

[Learner's latest message]
{normalized_user_input}
{numeric_equation_block}

Return SOLVED when the latest message states the correct final answer for every
required part of the CURRENT named item, even if it is short or corrects an
earlier mistake.
Return INCORRECT only when the latest message attempts the requested final
answer for the current item or makes a concrete verifiably wrong claim about a
needed step. Do NOT mark an answer INCORRECT merely because it answers
Isabella's narrower guiding question instead of the original item.
Return UNCLEAR when it is partial, procedural, ambiguous, a question, or makes
no verifiable answer claim.

Correct intermediate quantities are UNCLEAR, not SOLVED and not INCORRECT. If
the current item asks for a final amount, value, expression, model, or result,
then an answer that only gives a helper quantity such as a period count,
frequency, rate per period, multiplier, base amount, exponent, coefficient,
substituted input, or setup component is incomplete. Mark it UNCLEAR even when
that helper quantity is correct.

If Isabella's most recent question asked for a helper quantity, classify the
learner's direct answer to that helper question as UNCLEAR unless the same
message also states the original item's requested final answer. The completion
status is about the original current item, not about whether Isabella's latest
guiding question was answered.

For items that ask for a final amount, value, numerical result, balance, total,
distance, probability, measurement, or other computed quantity, a fully
substituted model expression is still intermediate. Mark it UNCLEAR until the
learner evaluates it to the requested quantity, unless the original item
explicitly asks for an expression, equation, model, formula, or setup.

First identify exactly what the CURRENT named item asks the learner to find.
That current item controls completion, not sibling cases and not a narrower
question Isabella asked while guiding the learner. Set "contains_final_answer"
to true only when the latest message explicitly states the requested result for
the current item.
Do not infer an unstated final answer merely because the learner wrote an
equation, substitution, transformation, or setup from which it could be
solved. A fully substituted expression, equation, ordered pair, or exact
formula counts as a final answer ONLY when the current item asks for an
expression, equation, model, formula, point, ordered pair, or other
representation rather than a simplified value.

For function-evaluation tasks of the form "Let f(x)=... evaluate f(a)", a
response that only substitutes a into the defining formula is NOT a final
answer. For example, if f(x)=b^x, then "b^a" is a substitution step for f(a),
not an evaluated value. When the input a is negative, fractional, radical, or
irrational, require a numerical value or decimal approximation unless the item
explicitly asks for an exact symbolic form. Do not mark direct substitution,
reciprocal-power form, radical form, or fractional-power form as SOLVED merely
because it is mathematically equivalent. If it is mathematically equivalent but
not evaluated enough, return UNCLEAR rather than INCORRECT.

Apply this function-evaluation rule strictly:
- If f(x)=b^x and the item asks for f(a), the answer "b^a" is UNCLEAR.
- If a is a negative fraction, rewriting "b^a" as a reciprocal with the same
  fractional exponent, a radical, or another fractional-power expression is
  still UNCLEAR until it is evaluated numerically.
- If a is irrational and no simpler exact form exists, the direct expression
  "b^a" is still UNCLEAR for an "evaluate" task; a numerical approximation is
  the evaluated value.

For expression/model/formula tasks, a fully substituted exact expression can
count as a final answer when it directly represents the requested expression,
equation, model, formula, or setup and all item-specific values are included.
When the problem provides a template containing one unknown parameter and asks
the learner to identify the resulting expression, an explicit correct value of
that parameter is sufficient if it uniquely determines the requested expression.

Judge mathematical meaning, not presentation. Accept harmless informal
formatting when the intended answer is unambiguous. For a requested ordered
pair or vector, accept two clearly stated comma-separated values without
requiring parentheses or angle brackets. Do not require units, a sentence, or
an explanation unless the problem explicitly requires one.

Interpret numeric equations generously:
- Treat commas inside numbers as thousands separators, not as list separators.
  For example, "1,425.7608" means 1425.7608.
- Treat multiplication as commutative when checking a final numeric equation.
  For example, "1.03^12 * 1000 = 1425.7608" and
  "1000 * 1.03^12 = 1425.7608" have the same mathematical meaning.
- If the latest message includes a numeric equation whose right-hand side or
  clearly stated result is the correct requested final amount/value, return
  SOLVED even if the expression is written in a different but equivalent order.
- Do not mark a correct numeric final amount INCORRECT merely because the
  accompanying expression is informally typed with "^", omitted multiplication
  signs, or a different multiplication order.

Equivalent final forms count as final answers when they match the representation
the current item requests. If the current item asks for an expression, equation,
point, exact symbolic value, or model, accept any mathematically equivalent
exact form unless the original problem explicitly demands a particular
representation (for example: decimal approximation, simplified radical form,
positive exponents only, factored form, expanded form, or a rounded value). For
direct function-evaluation tasks, do not accept an unevaluated substitution
expression merely because it is equivalent after simplification.

Interpret common typed math generously before judging:
- Treat "^" as exponentiation.
- Infer ordinary grouping from context when a learner types informal math, such
  as negative exponents, fractional exponents, roots, reciprocals, fractions,
  omitted multiplication signs, or missing outer parentheses.
- If the intended expression is still ambiguous, return UNCLEAR and ask for
  notation clarification rather than marking it wrong.

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
        if status == "INCORRECT" and _allow_equation_fallback:
            for _, stated_raw, _, _ in get_self_consistent_numeric_equations(user_input):
                fallback_status = assess_latest_answer(
                    stated_raw,
                    image_paths=image_paths,
                    image_urls=image_urls,
                    _allow_equation_fallback=False,
                )
                if fallback_status == "SOLVED":
                    dprint("[Answer judge] SOLVED: numeric equation fallback matched final value.")
                    return "SOLVED"
        dprint(f"[Answer judge] {status}: {calculation}")
        return status
    except Exception as e:
        dprint(f"[Answer judge] Failed; using UNCLEAR: {e!s:.200s}")
        return "UNCLEAR"


def _fallback_solved_ack(is_last_problem: bool) -> str:
    if is_last_problem:
        options = [
            "That finishes it. I like how you landed the final answer cleanly.",
            "You got the last one too. We made it through the whole set.",
            "That wraps up the example. Your final answer checks out.",
            "Yep, that completes the set. You kept the reasoning on track.",
        ]
    else:
        options = [
            "That works. You finished this part, so let's move to the next one.",
            "Yep, that settles this part. Your answer matches what the problem asks.",
            "That checks out. You solved this one, so we can keep going.",
            "Right, that completes this subproblem. Nice and clean.",
            "Exactly, this part is done. Let's carry that idea into the next one.",
        ]
    return random.choice(options)


def build_solved_reply(
    user_input: str,
    is_last_problem: bool,
    image_paths: list[str] | None = None,
    image_urls: list[str] | None = None,
) -> str:
    """Build a varied Isabella acknowledgement while preserving control markers."""
    descriptor = get_problem_descriptor()
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
    history_lines.append(f"Learner: {user_input}")
    history = "\n".join(history_lines)

    dev_message = f"""
Only speak English. You are Isabella, a calm learning buddy.

[Task]
The learner just solved {descriptor}. Write only Isabella's visible
acknowledgement line. Do not include [EOP] or [EOF]; the program will add those.

[Tone]
- Sound like a real peer noticing that this subproblem is complete, not a
  template or grading rubric.
- Vary the wording. Do not use or imitate "That's correct; you completed this
  problem."
- Do not begin with "That's correct."
- Briefly acknowledge the learner's specific answer or reasoning when the
  dialogue gives enough information.
- For a normal completed subproblem, signal that this part is done and that you
  can continue.
- For the final completed problem, signal that the whole example/set is done.
- Keep it to 8-18 words, one sentence, no question mark, no exclamation mark.
"""
    user_message = f"""[Current-problem dialogue]
{history}

This {"is" if is_last_problem else "is not"} the final problem in the current
example set. Write Isabella's varied completion acknowledgement now.
"""

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

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1",
            messages=cast(Any, [
                {"role": "developer", "content": dev_message},
                {"role": "user", "content": user_content},
            ]),
            temperature=0.8,
            max_tokens=60,
        )
        visible_reply = strip_untrusted_control_markers(response.choices[0].message.content or "")
    except Exception as e:
        dprint(f"[Solved reply] Failed; using fallback: {e!s:.200s}")
        visible_reply = ""

    visible_reply = visible_reply.strip().strip('"').strip("'")
    word_count = len(re.findall(r"\b[\w'-]+\b", visible_reply))
    if (
        not visible_reply
        or "?" in visible_reply
        or "!" in visible_reply
        or word_count > 22
        or "completed this problem" in visible_reply.lower()
        or visible_reply.lower().startswith("that's correct")
    ):
        visible_reply = _fallback_solved_ack(is_last_problem)

    reply = f"[EOP]\n{visible_reply}"
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
    compound_question = re.search(
        r"\b(?:and|or)\s+(?:how|what|why|when|where|which|can|could|would|will|do|does|did|is|are)\b",
        visible_reply,
        re.IGNORECASE,
    )
    validation_opener = re.match(
        r"^(?:yes|that's right|correct|you're right|right|you said|you noticed|great|good|nice|thanks)\b",
        visible_reply,
        re.IGNORECASE,
    )
    premature_rate_multiplier = re.search(
        r"\bwhat\s+does\s+multipl\w+\s+by\s+0\.\d+",
        visible_reply,
        re.IGNORECASE,
    )
    formula_delivery = re.search(
        r"\bformula\b.*\b(?:helps|is|with|like)\b|[A-Za-z]\s*=\s*[A-Za-z0-9(]",
        visible_reply,
        re.IGNORECASE,
    )
    direct_check_prompt = re.search(
        r"\b(?:let'?s check|check your|step by step|multiply it out|calculate|simplify|solve it)\b",
        visible_reply,
        re.IGNORECASE,
    )
    function_eval_representation_loop = (
        re.search(r"\brepresent\b", visible_reply, re.IGNORECASE) is not None
        and re.search(r"\b(?:substitut|f\(x\)|f\s*\()", visible_reply, re.IGNORECASE) is not None
    )
    expression_representation_loop = (
        re.search(r"\brepresent\b", visible_reply, re.IGNORECASE) is not None
        and re.search(r"(?:\$.*?[+\-*/^].*?\$|\d+\s*(?:\^|\*\*|\*|×)\s*\(?\d)", visible_reply) is not None
    )
    previous_value_loop = re.search(
        r"\b(?:stay|stays|still|same|like before)\b",
        visible_reply,
        re.IGNORECASE,
    )
    return (
        visible_reply.count("?") != expected_question_marks
        or word_count > 35
        or compound_question is not None
        or validation_opener is not None
        or premature_rate_multiplier is not None
        or formula_delivery is not None
        or direct_check_prompt is not None
        or function_eval_representation_loop
        or expression_representation_loop
        or previous_value_loop is not None
    )


def simplify_compound_question(reply: str) -> str:
    """Keep Socratic turns to one conceptual question."""
    return re.sub(
        r"\s*,?\s+\b(?:and|or)\s+(?:how|what|why|when|where|which|can|could|would|will|do|does|did|is|are)\b.*\?\s*$",
        "?",
        reply.strip(),
        flags=re.IGNORECASE,
    )


def collapse_extra_question_marks(reply: str) -> str:
    """Keep the final educational question instead of comma-splicing questions."""
    cleaned = reply.strip()
    if cleaned.count("?") <= 1:
        return cleaned

    questions = re.findall(r"[^?]*\?", cleaned)
    if questions:
        final_question = questions[-1].strip()
        return final_question[0].upper() + final_question[1:]
    return cleaned


def rewrite_stays_same_question(reply: str) -> str:
    """Turn repeated previous-value checks into forward-looking questions."""
    cleaned = reply.strip()
    already_rewritten = re.search(
        r"^what\s+does\s+(.+?)\s+still\s+become\s+instead\?\s*$",
        cleaned,
        re.IGNORECASE,
    )
    if already_rewritten:
        subject = already_rewritten.group(1).strip()
        return f"What does {subject} become instead?"

    direct_stay = re.search(
        r"\bdoes\s+(.+?)\s+(?:stay|stays|remain|remains)\s+(?:at|the same as|like)\b.*\?\s*$",
        cleaned,
        re.IGNORECASE,
    )
    if direct_stay:
        subject = direct_stay.group(1).strip()
        return f"What does {subject} become instead?"

    implied_stay = re.search(
        r"\bdoes\s+that\s+(?:also\s+)?mean\s+(.+?)\s+(?:is|are)\s+still\b.*\?\s*$",
        cleaned,
        re.IGNORECASE,
    )
    if implied_stay:
        subject = implied_stay.group(1).strip()
        return f"What does {subject} become instead?"

    return cleaned


def cleanup_comma_splice_questions(reply: str) -> str:
    """Fix common generated comma splices before a question clause."""
    return re.sub(
        r",\s+(Can|Could|Would|Will|Do|Does|Did|Is|Are|Why|What|How|When|Where|Which)\b",
        r". \1",
        reply.strip(),
    )


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
    reply = cleanup_comma_splice_questions(reply)
    reply = simplify_compound_question(reply)
    reply = rewrite_stays_same_question(reply)
    reply = collapse_extra_question_marks(reply)

    if reply_needs_shape_repair(reply):
        repair_messages = cast(Any, messages + [
            {"role": "assistant", "content": reply},
            {"role": "developer", "content": (
                "Rewrite the immediately preceding draft only. The problem is still "
                "active, so do not output [EOP] or [EOF]. Use no more than 35 visible "
                "words and exactly one question mark. Keep it "
                "grounded, use at most one small hint, reveal no final answer, and "
                "introduce no new facts or topic labels. If the learner's attempt "
                "is incorrect, do not say \"That's incorrect\" or give the correction; "
                "do not thank, praise, validate, or say \"Try\". If the teaching "
                "strategy is protege_effect, preserve that strategy: stay in learner "
                "mode. On the first Protege turn, give one plausible wrong reasoning "
                "chain that is actually wrong for the current case, then ask the learner "
                "to explain why that reasoning is wrong. Do not present a correct method "
                "as vague uncertainty. "
                "After the learner corrects it, do not introduce a new unrelated "
                "mistake; ask for their explanation, the next adapted value, or the "
                "current expression. Do not ask whether the same rejected wrong idea is "
                "actually correct; ask what the corrected value/count/relationship is "
                "or why it changes. If the learner already stated the corrected piece, "
                "ask why that correction is true or how it changes the next setup piece. "
                "After a correction, do not ask whether another value stays the same "
                "or is still the previous case's value; ask what it becomes instead. "
                "If the teaching strategy is "
                "worked_example_fading, preserve that strategy: anchor to "
                "the previous solved case and ask what changes or what adapted piece "
                "comes next. Otherwise ask one Socratic diagnostic or targeted-check "
                "question with no multi-part phrasing joined by \"and\" or \"or\". "
                "If the learner gave a substituted or model expression for an item "
                "that asks for an amount, value, balance, total, or result, ask what "
                "numerical amount/value it gives before using the bare-final-answer "
                "fallback. Do not ask only what the expression represents. If the learner "
                "gave only a final answer, use only this shape: "
                "\"Why did you think it was <their answer>?\" Do not infer reasoning "
                "from Isabella's previous question. Do not ask them to check, calculate, "
                "multiply, simplify, solve, or work step by step before they reveal "
                "their reasoning unless they gave a substituted expression that still "
                "needs evaluation. If the learner's reasoning is "
                "visible, restate it as a statement, not a question, then ask one "
                "observation question about their work. Do not use the word \"should\" "
                "for visible incorrect reasoning. If they show an arithmetic expression, "
                "ask only about that expression, not the rule. For repeated multiplication, "
                "ask only how many factors they wrote; do not mention the exponent, "
                "substitution value, or correct count. For useful intermediate answers, "
                "do not start with \"Great\", \"Good\", \"Nice\", \"Yes\", \"That's right\", \"Right\", "
                "\"Correct\", or \"You're right\"; "
                "do not start by paraphrasing with \"You said\" or \"You noticed\". "
                "Ask only one thing: why it works, what it represents, how to check it, "
                "or what follows. If a quantity has multiple parts, ask about one part "
                "at a time. If the learner gives only a useful number or expression, ask "
                "what it represents before introducing a new operation with it. Do not "
                "ask how to use that number or expression in the same reply. For rates "
                "and percentages, ask what base quantity the rate applies to or what "
                "one-period change it creates before asking about a multiplier or formula. "
                "Do not say \"multiplying by <rate>\" yet. If the learner asks for a "
                "formula, method, rule, or procedure, do not provide the formula or "
                "symbolic template; ask about one known quantity, repeated change, or "
                "meaning first. For protege_effect, do not solve the near-miss yourself; "
                "the learner should do the explaining. For "
                "worked_example_fading, keep the previous-case anchor "
                "short. If the learner identified one changed input, parameter, count, "
                "condition, or case feature, ask for the next linked changed quantity "
                "or relationship needed to adapt the previous solution. You may ask for "
                "two tightly linked changed values when both adapt the prior example. "
                "If the draft contains a phrase "
                "like \"and how\" or \"and what\", keep only the first conceptual question "
                "and delete the rest. "
                "Output only the rewrite."
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
        reply = cleanup_comma_splice_questions(reply)
        reply = simplify_compound_question(reply)
        reply = rewrite_stays_same_question(reply)
        reply = collapse_extra_question_marks(reply)

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

    default_example_path = get_first_example_image_path()
    image_prompt_hint = (
        f"press Enter for {Path(default_example_path).name}"
        if default_example_path
        else "press Enter to skip"
    )
    image_ref = input(
        f"Enter an image path or URL ({image_prompt_hint}): "
    ).strip().strip('"').strip("'")
    if not image_ref and default_example_path:
        image_ref = default_example_path

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
            reply_strategy = determine_teaching_strategy_for_problem(
                CURRENT_PROBLEM,
                image_paths=image_paths or None,
                image_urls=image_urls or None,
            )
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

            print_isabella_reply(opener_reply, reply_strategy)
            dprint(f"🎯 Opener latency: {time.time() - opener_start:.4f}s")

        raw_input_str = input("You: ").strip()
        if not raw_input_str:
            dprint("Ending conversation.")
            break

        user_input = raw_input_str

        start_total = time.time()
        reply_strategy = get_current_teaching_strategy()
        answer_status = assess_latest_answer(
            user_input,
            image_paths=image_paths or None,
            image_urls=image_urls or None,
        )
        if answer_status == "SOLVED":
            ai_reply = build_solved_reply(
                user_input,
                CURRENT_PROBLEM >= TOTAL_PROBLEMS,
                image_paths=image_paths or None,
                image_urls=image_urls or None,
            )
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

        print_isabella_reply(ai_reply, reply_strategy)
        dprint(f"🎯 총 체감 레이턴시(Total Latency): {time.time() - start_total:.4f}초")

        if all_done:
            break
