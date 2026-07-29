import os
import sys
import atexit
from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer

from openai import OpenAI
from ai_friend_decision import make_decision as make_jiho_decision
from ai_friend_eval import EXPORT_FILE, export_to_jsonl as export_turn_to_jsonl
from ai_friend_eval import update_affinity as evaluate_affinity_delta
from jiho_memory_repository import JihoMemoryRepository
from ai_friend_prompt_builder import build_runtime_prompt
from ai_friend_response import generate_response as generate_jiho_response
from ai_friend_response import split_double_text
from ai_friend_state import JihoRuntimeState
from jiho_prompt import ROLE_DISPLAY

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

runtime_state = JihoRuntimeState()

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
    return runtime_state.time_context_tracker.get_time_context()


def _consume_time_context_for_turn() -> tuple[str, str | None]:
    return runtime_state.time_context_tracker.consume_for_turn()


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
    result = make_jiho_decision(
        openai_client=openai_client,
        user_input=user_input,
        long_term_memories=long_term_memories,
        time_str=time_str,
        time_ctx=time_ctx,
        affinity=runtime_state.affinity,
        conversation_history=runtime_state.conversation_history,
        cooldown_until=runtime_state.cooldown_until,
        cooldown_reason=runtime_state.cooldown_reason,
        last_response_time=runtime_state.last_response_time,
    )
    runtime_state.cooldown_until = result.cooldown_until
    runtime_state.cooldown_reason = result.cooldown_reason
    return result.decision


# ── 호감도 갱신 ───────────────────────────────────────────────────────
def update_affinity(agent_emotion_info: dict, user_input: str, ai_reply: str) -> tuple[int, str]:
    """CLI/scenario-only legacy wrapper for affinity evaluation."""
    return evaluate_affinity_delta(
        openai_client=openai_client,
        role_display=ROLE_DISPLAY,
        conversation_history=runtime_state.conversation_history,
        current_affinity=runtime_state.affinity,
        agent_emotion_info=agent_emotion_info,
        user_input=user_input,
        ai_reply=ai_reply,
    )

# ── 대화 히스토리 추가 ────────────────────────────────────────────────
def add_to_history(role: str, text: str) -> None:
    runtime_state.add_message(role, text)
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
    return build_runtime_prompt(
        user_input=user_input,
        affinity=runtime_state.affinity,
        conversation_history=runtime_state.conversation_history,
        memory_loader=get_long_term_memory,
        time_context_loader=_get_time_context,
        agent_emotion_info=agent_emotion_info,
        long_term_memories=long_term_memories,
        long_term_k=long_term_k,
        decision=decision,
        time_str=time_str,
        time_ctx=time_ctx,
        debug_prompt=DEBUG_PROMPT,
    )

# ── GPT 답변 생성 (2nd API call) ──────────────────────────────────────
def generate_ai_response(prompt_text: str) -> str:
    """2nd call: 단일 답변 텍스트 반환. 연톡 분리는 _split_double_text()에서 처리."""
    text, usage = generate_jiho_response(openai_client, prompt_text)
    runtime_state.last_response_usage = usage
    return text


def _split_double_text(text: str) -> list[str]:
    return split_double_text(text)

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
