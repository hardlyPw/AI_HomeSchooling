import os
import sys
import json
import atexit
from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer

from datetime import datetime

from openai import OpenAI
import time
from ai_friend_eval import EXPORT_FILE, export_to_jsonl as export_turn_to_jsonl
from ai_friend_eval import update_affinity as evaluate_affinity_delta
from jiho_decision_prompt import render_jiho_decision_prompt
from jiho_memory_repository import JihoMemoryRepository
from jiho_prompt import ROLE_DISPLAY, render_jiho_prompt

# Windows cp949 환경에서도 한글/특수문자(em dash 등) 출력 안전하게
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

load_dotenv()

url: str = str(os.getenv("SUPABASE_URL", ""))
key: str = str(os.getenv("SUPABASE_KEY", ""))
if not url or not key:
    raise ValueError("❌ .env 파일에서 URL이나 KEY를 읽어오지 못했습니다.")
supabase: Client = create_client(url, key)

openai_key: str = str(os.getenv("OPENAI_API_KEY", ""))
if not openai_key:
    raise ValueError("❌ .env 파일에서 OPENAI_API_KEY를 읽어오지 못했습니다.")
openai_client = OpenAI(api_key=openai_key)

print("모델 로딩 중...")
model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
print("모델 로드 완료!")

# ── 페르소나 분리: AI_Friend 전용 테이블/RPC ─────────────────────────
MEMORY_TABLE = "friend_memories_v2"
MEMORY_MATCH_RPC = "match_friend_memories_v2"

# ── RAG 트리거 정책: session 단위 consolidation ────────────────────
# 턴 threshold는 사용하지 않음. session_break(decision layer) /
# 5분 무대화 timeout / atexit 중 하나가 와야 chunk flush.
SESSION_TIMEOUT_SECONDS = 5 * 60

DEBUG_PROMPT = True  # True 로 설정하면 프롬프트 조립 과정을 출력

# ── 평가 모드 플래그 ───────────────────────────────────────────────────
# False = 페르소나 단독 평가 (장기기억 검색·저장 모두 OFF)
# True  = 풀 시스템 (RAG 활성화)
USE_LONG_TERM_MEMORY = True

_memory_repository = JihoMemoryRepository(
    supabase_client=supabase,
    embedding_model=model,
    openai_client=openai_client,
    memory_table=MEMORY_TABLE,
    memory_match_rpc=MEMORY_MATCH_RPC,
    session_timeout_seconds=SESSION_TIMEOUT_SECONDS,
    uses_long_term_memory=lambda: USE_LONG_TERM_MEMORY,
)

affinity: int = 70             # 호감도 (0~100)
consecutive_negative: int = 0  # 연속 마이너스 횟수

# ── 쿨다운 / 행동 레이어 상태 ──────────────────────────────────────
_cooldown_until: datetime | None = None
_cooldown_reason: str = ""
_last_response_time: datetime = datetime.now()

# 프로세스 종료 시 pending 세션 자동 마무리 (KeyboardInterrupt 포함)
atexit.register(lambda: memory_shutdown())

# ── 단기기억 시드 ────────────────────────────────────────────────────
# main 시작 시 conversation_history에 부어넣어서 자연스러운 follow-up 컨텍스트 제공
INITIAL_HISTORY: list[dict] = [
    {"role": "user", "text": "yo did you do the math hw"},
    {"role": "ai",   "text": "barely started. you?"},
    {"role": "user", "text": "i'm cooked, the function stuff makes no sense"},
    {"role": "ai",   "text": "which part. just send what you got"},
    {"role": "user", "text": "last 4 problems. plotting points and lines"},
    {"role": "ai",   "text": "those are easy, plug in x get y. come over after band ill show u"},
    {"role": "user", "text": "for real? you free tonight"},
    {"role": "ai",   "text": "yea around 7. moms making pasta"},
    {"role": "user", "text": "bet. how was band today"},
    {"role": "ai",   "text": "drumline ran the new piece. i kinda rushed the bridge"},
    {"role": "user", "text": "oof did coach say anything"},
    {"role": "ai",   "text": "made me play it solo like three times. embarrassing"},
    {"role": "user", "text": "thats rough man"},
    {"role": "ai",   "text": "whatever ill fix it tomorrow"},
    {"role": "user", "text": "lol respect. anyway i gotta walk the dog brb"},
    {"role": "ai",   "text": "k"},
    {"role": "user", "text": "back. dog ate half a sock somehow"},
    {"role": "ai",   "text": "bro your dog is unhinged"},
    {"role": "user", "text": "tell me about it. anyway see u at 7"},
    {"role": "ai",   "text": "k dont be late this time"},
]

conversation_history: list[dict] = []

# ── 장기기억: repository wrapper ───────────────────────────────────
def get_long_term_memory(query_text: str, top_k: int = 5) -> list[dict]:
    return _memory_repository.get_long_term_memory(query_text, top_k=top_k)


def _drain_pending_chunk() -> list[dict]:
    return _memory_repository.drain_pending_chunk()


def record_turn(user_text: str, ai_text: str, session_break: bool = False) -> None:
    _memory_repository.record_turn(user_text, ai_text, session_break=session_break)


def memory_shutdown() -> None:
    """프로세스 종료 시 pending 세션을 chat 으로 마무리."""
    _memory_repository.shutdown()

# ── 행동 결정 레이어 (1st API call) ─────────────────────────────────
def _get_time_context() -> tuple[str, str]:
    now = datetime.now()
    time_str = now.strftime("%I:%M %p")
    h = now.hour
    if 6 <= h < 8:
        ctx = "early morning, getting ready for school"
    elif 8 <= h < 15:
        ctx = "school hours"
    elif 15 <= h < 18:
        ctx = "after school, free time"
    elif 18 <= h < 21:
        ctx = "evening at home"
    elif 21 <= h < 24:
        ctx = "late for a 7th grader"
    else:
        ctx = "middle of the night"
    return time_str, ctx


# Buckets that trigger Jiho's "flag the time" reflex. After the first turn that
# hits one of these in a session, we suppress the time context so Jiho stops
# harping on it (otherwise late-night → he keeps telling the user to sleep).
_NOTEWORTHY_TIME_CTXS = {
    "early morning, getting ready for school",
    "school hours",
    "late for a 7th grader",
    "middle of the night",
}
_session_time_buckets_seen: set[str] = set()


def _consume_time_context_for_turn() -> tuple[str, str | None]:
    """Per-turn time context with session-level suppression.

    Returns (time_str, time_ctx). time_ctx is None when the current bucket has
    already been flagged this session — callers should omit the time label /
    [Current Time] section so the late-night / school-hours reflex doesn't
    re-fire. Mutates _session_time_buckets_seen, so call once per turn.
    """
    time_str, time_ctx = _get_time_context()
    if time_ctx in _NOTEWORTHY_TIME_CTXS:
        if time_ctx in _session_time_buckets_seen:
            return time_str, None
        _session_time_buckets_seen.add(time_ctx)
    return time_str, time_ctx


def make_decision(
    user_input: str,
    long_term_memories: list[dict],
    time_str: str,
    time_ctx: str | None,
) -> dict:
    """1st API call: Jiho의 감정 + 행동 방식을 한 번에 추출 (timing, action, emotion).

    time_ctx == None means the current bucket was already flagged this session,
    so we hide the bucket label from the decision layer — that way it stops
    picking wrap_up / drift-to-sleep based on the same late-night cue.
    """
    global _cooldown_until, _cooldown_reason

    came_back_from = None
    if _cooldown_until is not None:
        mins_away = max(1, int((_cooldown_until - _last_response_time).total_seconds() / 60))
        came_back_from = f"away ~{mins_away} min ({_cooldown_reason})"
        _cooldown_until = None
        _cooldown_reason = ""

    system_prompt = render_jiho_decision_prompt(
        user_input=user_input,
        long_term_memories=long_term_memories,
        time_str=time_str,
        time_ctx=time_ctx,
        affinity=affinity,
        conversation_history=conversation_history,
        came_back_from=came_back_from,
    )

    try:
        start = time.time()
        resp = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
            max_tokens=200,
            temperature=0.6,
            response_format={"type": "json_object"},
        )
        raw = (resp.choices[0].message.content or "").strip()
        decision = json.loads(raw)
        if getattr(resp, "usage", None) is not None:
            decision["_usage"] = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
            }
        print(f"[Decision] {time.time() - start:.2f}s → "
              f"timing={decision.get('timing')}, action={decision.get('action')}, "
              f"break={decision.get('session_break')}, "
              f"aff_delta={decision.get('affinity_delta', 0)}, "
              f"reason={decision.get('reasoning', '')}")
    except Exception as e:
        print(f"[Decision] 실패, 기본값: {e}")
        decision = {"timing": "instant", "action": "normal", "session_break": False, "reasoning": "fallback"}

    if decision.get("timing") not in ("instant", "delayed", "double_text", "wrap_up"):
        decision["timing"] = "instant"
    if decision.get("action") not in ("normal", "topic_drift", "memory_flashback"):
        decision["action"] = "normal"
    decision["session_break"] = bool(decision.get("session_break", False))
    # wrap_up은 Jiho가 떠나는 거니까 자동으로 세션 종료로 간주
    if decision["timing"] == "wrap_up":
        decision["session_break"] = True

    try:
        decision["affinity_delta"] = max(-10, min(10, int(decision.get("affinity_delta", 0))))
    except (TypeError, ValueError):
        decision["affinity_delta"] = 0
    if not isinstance(decision.get("affinity_reason"), str):
        decision["affinity_reason"] = ""

    if came_back_from:
        decision["came_back_from"] = came_back_from

    return decision


# ── 호감도 갱신 ───────────────────────────────────────────────────────
def update_affinity(agent_emotion_info: dict, user_input: str, ai_reply: str) -> tuple[int, str]:
    """CLI/scenario-only legacy wrapper for affinity evaluation."""
    return evaluate_affinity_delta(
        openai_client=openai_client,
        role_display=ROLE_DISPLAY,
        conversation_history=conversation_history,
        current_affinity=affinity,
        agent_emotion_info=agent_emotion_info,
        user_input=user_input,
        ai_reply=ai_reply,
    )

# ── 대화 히스토리 추가 ────────────────────────────────────────────────
def add_to_history(role: str, text: str) -> None:
    conversation_history.append({"role": role, "text": text})
    # 장기기억 트리거는 main 루프의 record_turn(user, ai)에서 처리

# ── 프롬프트 조립 ────────────────────────────────────────────────────
def build_prompt(
    user_input: str,
    agent_emotion_info: dict | None = None,
    long_term_memories: list[dict] | None = None,
    long_term_k: int = 5,
    decision: dict | None = None,
    time_str: str | None = None,
    time_ctx: str | None = None,
) -> str:
    # 외부에서 미리 조회된 장기기억이 없으면 직접 조회 (하위 호환)
    long_term = long_term_memories if long_term_memories is not None else get_long_term_memory(user_input, top_k=long_term_k)

    if DEBUG_PROMPT:
        SEP = "─" * 60
        print(f"\n{'━'*60}")
        print("[DEBUG] 프롬프트 조립 과정")
        print(f"{'━'*60}")
        print(f"[1] 유저 입력:\n  {user_input}")
        if agent_emotion_info:
            print(SEP)
            print(f"[1-1] Agent 감정 분석: {agent_emotion_info}")
        print(SEP)
        print(f"[2] 장기기억 검색 결과 (top {long_term_k}):")
        if long_term:
            for i, m in enumerate(long_term, 1):
                print(f"  [{i}] (score={m['score']}) {m['description'][:80]}{'...' if len(m['description']) > 80 else ''}")
        else:
            print("  (없음)")
        print(SEP)
        print(f"[3] 단기기억 (최근 대화 {len(conversation_history)}개):")
        if conversation_history:
            for m in conversation_history[-6:]:  # 마지막 6개만 미리보기
                label = ROLE_DISPLAY.get(m['role'], m['role'])
                print(f"  {label}: {m['text'][:60]}{'...' if len(m['text']) > 60 else ''}")
            if len(conversation_history) > 6:
                print(f"  ... (상위 {len(conversation_history) - 6}개 생략)")
        else:
            print("  (없음)")
        print(SEP)

    # 시그니처를 추가하기 전 호출하는 코드와의 하위호환을 위해 fallback 처리.
    # 정상 경로는 main 루프에서 _consume_time_context_for_turn() 결과를 넘겨준다.
    if time_str is None:
        time_str, time_ctx = _get_time_context()

    prompt = render_jiho_prompt(
        user_input=user_input,
        affinity=affinity,
        long_term_memories=long_term,
        long_term_k=long_term_k,
        conversation_history=conversation_history,
        agent_emotion_info=agent_emotion_info,
        decision=decision,
        time_str=time_str,
        time_ctx=time_ctx,
    )

    if DEBUG_PROMPT:
        print(f"[4] 최종 프롬프트 (총 {len(prompt)}자):")
        print(prompt)
        print("━" * 60)

    return prompt

# ── GPT 답변 생성 (2nd API call) ──────────────────────────────────────
last_response_usage: dict | None = None


def generate_ai_response(prompt_text: str) -> str:
    """2nd call: 단일 답변 텍스트 반환. 연톡 분리는 _split_double_text()에서 처리."""
    global last_response_usage
    print("\nGPT 답변 생성 중...")
    start = time.time()
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "system", "content": prompt_text}],
        temperature=0.8,
        max_tokens=300,
    )
    print(f"[Latency] GPT 답변: {time.time() - start:.4f}초")
    last_response_usage = (
        {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
        }
        if getattr(response, "usage", None) is not None
        else None
    )
    return response.choices[0].message.content or "brb, gimme a sec"


def _split_double_text(text: str) -> list[str]:
    """연톡 분리: 온점 기준 → 없으면 50% 단어 경계. Always max 2 beats."""
    parts = [p.strip() for p in text.split('.') if p.strip()]
    if len(parts) >= 2:
        # Cap at 2 beats: first sentence stays as beat 1, rest joined into beat 2.
        beat1 = parts[0]
        beat2 = ". ".join(parts[1:])
        return [beat1, beat2]

    words = text.split()
    if len(words) >= 4:
        mid = len(words) // 2
        return [" ".join(words[:mid]), " ".join(words[mid:])]

    return [text]

# ── JSONL Export for Autorater ──────────────────────────────────────
def export_to_jsonl(
    user_input: str,
    ai_reply: str,
    affinity_at_response: int,
    consecutive_neg: int,
    agent_emotion_info: dict | None = None,
) -> None:
    """CLI/scenario-only legacy wrapper for autorater export."""
    export_turn_to_jsonl(
        user_input=user_input,
        ai_reply=ai_reply,
        affinity_at_response=affinity_at_response,
        consecutive_neg=consecutive_neg,
        agent_emotion_info=agent_emotion_info,
        export_file=EXPORT_FILE,
    )

# ── 실행 ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    from ai_friend_cli import main

    main(sys.modules[__name__])
