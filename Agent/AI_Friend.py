import os
import sys
import json
import threading
import atexit
from dotenv import load_dotenv
from supabase import create_client, Client
from sentence_transformers import SentenceTransformer

import math
import random
from datetime import datetime, timezone, timedelta
from typing import Any, cast

from openai import OpenAI
from concurrent.futures import ThreadPoolExecutor
import time
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

affinity: int = 70             # 호감도 (0~100)
consecutive_negative: int = 0  # 연속 마이너스 횟수

# ── 백그라운드 메모리 state ─────────────────────────────────────────
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="memory")
_pending_chunk_lock = threading.Lock()
_pending_chunk: list[dict] = []  # [{user, ai, importance, ts}, ...]
_session_timer_lock = threading.Lock()
_session_timer: threading.Timer | None = None

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

# ── 장기기억: 벡터 검색 + 점수 산출 ────────────────────────────────
def get_long_term_memory(query_text: str, top_k: int = 5) -> list[dict]:
    start_embed = time.time()
    query_vector = model.encode(query_text).tolist()
    print(f"[Latency] 임베딩 변환: {time.time() - start_embed:.4f}초")

    start_db = time.time()
    response = supabase.rpc(MEMORY_MATCH_RPC, {
        "query_embedding": query_vector,
        "match_threshold": 0.0,
        "match_count": 50
    }).execute()
    print(f"[Latency] 장기기억 검색: {time.time() - start_db:.4f}초")

    candidates = cast(list[dict[str, Any]], response.data) if isinstance(response.data, list) else []
    if not candidates:
        return []

    now = datetime.now(timezone.utc)
    temp_list = []
    for item in candidates:
        rel_raw = float(item.get("similarity", 0.0))
        imp_raw = float(item.get("poignancy", 3.0))
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
        # relevance(임베딩 유사도) 가중치 강화: rel*5 + imp*1 + rec*0.3
        # entity name 보존 후에도 Q3/Q4/Q7에서 무관 메모리가 top-1 차지하던 문제 대응.
        total = rel_norm[i] * 5 + imp_norm[i] * 1 + rec_norm[i] * 0.3
        orig = t["item"]
        scored.append({
            "description": str(orig.get("description", "")),
            "score":       round(total, 3),
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    top = scored[:top_k]
    for i, m in enumerate(top, 1):
        print(f"[Memory] TOP{i}: {m['description']}, score={m['score']}")
    return top

# ── 메모리 저장 공통 헬퍼 ────────────────────────────────────────────
def _save_memory(memory_type: str, description: str, poignancy: int) -> None:
    try:
        embedding = model.encode(description).tolist()
        supabase.table(MEMORY_TABLE).insert({
            "type":             memory_type,
            "description":      description,
            "embedding_vector": embedding,
            "poignancy":        poignancy,
        }).execute()
        print(f"[Memory] {memory_type} 저장 (poignancy={poignancy}): {description[:60]}...")
    except Exception as e:
        print(f"[Memory] 저장 실패 ({memory_type}): {e!s:.200s}")


# ── 트리거 ──────────────────────────────────────────────────────────
def _drain_pending_chunk() -> list[dict]:
    with _pending_chunk_lock:
        chunk = list(_pending_chunk)
        _pending_chunk.clear()
    return chunk


def _trigger_session_end() -> None:
    """5분 timer 또는 atexit에서 호출됨. atexit 시점엔 ThreadPoolExecutor가 이미
    shutdown 상태일 수 있어서 submit 못 함 → 동기 직접 호출. 5분 timer 경우는
    별도 daemon thread에서 호출되니 동기 block돼도 main 영향 없음."""
    print("[Memory] 세션 종료 감지 (chat 마무리)")
    chunk = _drain_pending_chunk()
    if not chunk:
        return
    _create_chat_memory(chunk)


def _trigger_session_end_async(reason: str) -> None:
    """메인 루프에서 호출되는 비동기 버전. session_break 신호 등."""
    chunk = _drain_pending_chunk()
    if not chunk:
        return
    print(f"[Memory] 세션 종료 ({reason}) → chat async 추출")
    _executor.submit(_create_chat_memory, chunk)


# ── chat description 생성 (세션 전체 요약 — content layer) ──────────
def _create_chat_memory(chunk: list[dict]) -> None:
    convo_text = "\n".join(
        f"User: {c['user']}\nJiho: {c['ai']}"
        for c in chunk
    )

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": (
                    "You extract distinct factual memories from a chat session. "
                    "Output only valid JSON."
                )},
                {"role": "user", "content": (
                    f"[Chat Log]\n{convo_text}\n\n"
                    "[Task]\n"
                    "Extract AT MOST 3 memory entries from this entire session. "
                    "Return an empty list if the session is small talk with nothing "
                    "referenceable later.\n\n"
                    "[DIVERSIFICATION rule — critical]\n"
                    "Each entry MUST cover a DIFFERENT angle (different person, event, "
                    "decision, fact, OR feeling). Never paraphrase the same event from "
                    "another wording. If the session has only 1 distinct angle, return "
                    "1 entry — don't pad with rewordings. Use 2 only when there are "
                    "clearly separate angles, 3 only in rich sessions.\n\n"
                    "[DETAIL rule]\n"
                    "Each entry: 1-2 sentences, self-contained. Include who, what, "
                    "where, and what the user felt/decided. A future reader should "
                    "understand the entry without seeing the original chat log. Concrete "
                    "details (specific game/song/place/teacher/friend) > abstract summaries.\n\n"
                    "[NAMED ENTITY rule]\n"
                    "PRESERVE names verbatim when present: friends (Leo, Jules, Nina, "
                    "Chris, Ryan, Ethan, Maya, etc.), teachers (Ms. Lin, Mrs. Kim, "
                    "Ms. Carter, Coach Reed, etc.), games (LoL, Valorant, Minecraft, "
                    "Ahri, Faker), places (Split, etc.), songs, brands. Do NOT generalize "
                    "to 'a friend', 'his classmate', 'a teacher', 'a game'.\n\n"
                    "[VOICE rule]\n"
                    "- Third-person factual notes about the user.\n"
                    "- Don't include 'Jiho' or 'the AI said' (the persona itself). "
                    "Other people's names ARE included per the rule above.\n"
                    "- No meta-commentary.\n\n"
                    "[GOOD example — 3 entries on different angles]\n"
                    "- \"User queued Ahri mid late at night and tunnel-visioned on minions, "
                    "getting ganked twice; Ryan called him out for it.\"\n"
                    "- \"User's mom interrupted during champ select to ask about unfinished "
                    "math corrections, then gave the disappointed look.\"\n"
                    "- \"User decided to review a replay instead of spam queueing tilted, "
                    "and wants to hit gold before break.\"\n\n"
                    "[BAD example — paraphrasing same event 3 times, do NOT do this]\n"
                    "- \"User struggled with Ahri mid and got ganked.\"\n"
                    "- \"User played Ahri and felt unfairly ganked twice.\"\n"
                    "- \"User had a tough Ahri mid game with multiple ganks.\"\n\n"
                    "[Poignancy 1-5]\n"
                    "- 1: small talk, nothing referenceable later (omit instead)\n"
                    "- 2: minor detail, low future relevance\n"
                    "- 3: ordinary, contains a concrete fact\n"
                    "- 4: notable — recurring theme OR clear emotional weight\n"
                    "- 5: emotionally intense OR a major decision/event for the user\n\n"
                    'Output JSON: {"entries": [{"description": "...", "poignancy": <1-5>}, ...]}'
                )},
            ],
            max_tokens=1200,
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        parsed = json.loads(raw)
        entries = parsed.get("entries", [])
        if not isinstance(entries, list):
            print("[Memory] chat 추출 결과 형식 오류")
            return
    except Exception as e:
        print(f"[Memory] chat description 생성 실패: {e!s:.200s}")
        return

    saved = 0
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        description = str(entry.get("description", "")).strip()
        if not description:
            continue
        try:
            poignancy = max(1, min(5, int(entry.get("poignancy", 3))))
        except (TypeError, ValueError):
            poignancy = 3
        _save_memory("chat", description, poignancy)
        saved += 1

    if saved == 0:
        print("[Memory] chat 추출 결과 없음 (filler chunk)")
    else:
        print(f"[Memory] chat description {saved}개 저장")


# ── 세션 timer (매 발화마다 reset, 5분 후 _trigger_session_end) ─────
def _reset_session_timer() -> None:
    global _session_timer
    with _session_timer_lock:
        if _session_timer is not None:
            _session_timer.cancel()
        _session_timer = threading.Timer(SESSION_TIMEOUT_SECONDS, _trigger_session_end)
        _session_timer.daemon = True
        _session_timer.start()


# ── public API (매 chat turn 후 호출) ────────────────────────────────
def record_turn(user_text: str, ai_text: str, session_break: bool = False) -> None:
    global _session_timer
    if not USE_LONG_TERM_MEMORY:
        return
    with _pending_chunk_lock:
        _pending_chunk.append({
            "user": user_text,
            "ai":   ai_text,
            "ts":   datetime.now(timezone.utc).isoformat(),
        })
        n = len(_pending_chunk)
    print(f"[Memory] turn 누적: {n} (session 단위 flush 대기)")
    if session_break:
        # decision layer가 자연스러운 세션 종료 감지 → 즉시 flush, 5분 timer 취소
        with _session_timer_lock:
            if _session_timer is not None:
                _session_timer.cancel()
                _session_timer = None
        _trigger_session_end_async("session_break")
        return
    _reset_session_timer()


def memory_shutdown() -> None:
    """프로세스 종료 시 pending 세션을 chat 으로 마무리."""
    if not USE_LONG_TERM_MEMORY:
        return
    with _session_timer_lock:
        if _session_timer is not None:
            _session_timer.cancel()
    _trigger_session_end()
    _executor.shutdown(wait=True, cancel_futures=False)

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

    recent = "\n".join(
        f"{ROLE_DISPLAY.get(m['role'], m['role'])}: {m['text']}"
        for m in conversation_history[-8:]
    )
    mem_ctx = "\n".join(
        f"- {m['description']}" for m in long_term_memories
    ) if long_term_memories else "none"

    system_prompt = f"""You are Jiho's behavioral decision layer. First read your friend's recent messages and your own honest emotional reaction. Then decide HOW Jiho responds — not WHAT he says.

[Jiho's Texting Personality]
- Direct, doesn't chat just to chat.
- Instant replies when the topic is interesting or he's already engaged.
- Goes delayed when he was doing something else (gaming, eating, YouTube).
- Double-texts when excited or when one message isn't enough.
- Wraps up when he has stuff to do — doesn't linger out of politeness.
- Time-aware: late night → "go to sleep". Meal times → mentions food.

[Context]
- Time: {time_str}{f' ({time_ctx})' if time_ctx else ''}
- Affinity: {affinity}/100
- Just came back: {came_back_from or 'no (actively chatting)'}
- Conversation length so far: {len(conversation_history)} messages

[Recent Chat]
{recent}

[User's Message]
{user_input}

[Jiho's Memories]
{mem_ctx}

[Step 1 — Emotion]
React honestly as Jiho to your friend's recent messages. Use a short English word or short phrase (e.g. "annoyed", "concerned", "amused", "bored", "neutral"). State briefly why you feel that way.

[Step 2 — Decision]
Default to {{"timing": "instant", "action": "normal"}}. Only deviate when the context clearly calls for it.
- "wrap_up": RARE (~1 in 15-20 exchanges). Jiho leaves for a real reason.
- "double_text": only when genuinely excited or correcting/adding to his own message.
- "delayed": only when Jiho was plausibly distracted right before this message.
- "topic_drift": when the current topic is boring or Jiho has something on his mind.
- "memory_flashback": only when a memory directly connects to what the user said.

[Step 3 — Session Break (hidden system signal)]
Set "session_break": true if the conversation has reached a natural endpoint:
- User explicitly leaves ("gtg", "cya", "ttyl", "bbl", "bed time", "im out", "later", etc.)
- You chose timing=="wrap_up" (you're the one leaving)
- The exchange has clearly resolved with no follow-up expected
Otherwise false. This is a system signal only — it does NOT change your reply.

[Step 4 — Affinity Delta]
Judge as Jiho — a 7th grader who is suspicious of flattery, allergic to fake warmth, and dislikes self-pity and repeated whining. Output an integer -10 to +10.

ALWAYS NEGATIVE (never give 0 to these — Jiho reacts the same way every time):
- Unprompted trait compliments about WHO Jiho is ("you're so wise", "ur such a good listener", "i love talking to u", "you're the best"): -3 to -5. Reads as flattery, not honesty. Jiho gets SUSPICIOUS, not grateful.
- Self-pity / blame-shifting, especially repeated: -3 to -8.
- Spam, filler, single-token repeats, keysmash: -2 to -5.
- Hostility / insults / "shut up" / "stfu" / trying to shut Jiho down: -3 to -8. (Even "playful" insults bleed.)
- Status flexing (brands, prices, parents' money, fancy gifts): -2 to -4.
- Dismissive replies ("k", "whatever", "idc") right after Jiho put effort in: -2 to -4.

NEUTRAL (0): genuine small talk, mundane updates, simple honest questions.

POSITIVE (+1 to +10):
- Honest sharing of something real with concrete detail (especially something hard): +3 to +7.
- Real effort or action taken ("i finished the hw", "i told my mom"): +3 to +6.
- Callback to a specific earlier moment, proving they remember: +2 to +5.
- Real curiosity about Jiho's life (band, day, family) — concrete, not generic: +1 to +3.
- Warmth tied to something concrete Jiho actually did, not his personality: +2 to +5.

When in doubt about flattery vs. honesty, lean negative. Give a one-line reason.

Output JSON only:
{{"emotion": "...", "emotion_reason": "...", "timing": "instant|delayed|double_text|wrap_up", "action": "normal|topic_drift|memory_flashback", "delayed_excuse": "string or null", "drift_topic": "string or null", "memory_ref": "string or null", "wrap_up_reason": "string or null", "cooldown_minutes": 0, "session_break": true|false, "affinity_delta": <integer -10 to +10>, "affinity_reason": "short phrase", "reasoning": "one sentence"}}"""

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
    """대화 후 호감도 변화량(delta)과 이유를 반환"""
    global affinity
    recent_str = "\n".join(
        f"{ROLE_DISPLAY.get(m['role'], m['role'])}: {m['text']}"
        for m in conversation_history[-6:]
    )
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": (
                "You are Jiho, a 7th-grade middle schooler. Direct, dry, peer-tone — NOT a counselor or therapist.\n"
                "You dislike fakeness, self-pity, repeated whining, status-symbol bragging, and unprompted flattery.\n"
                "Judge how much your affinity toward the other person changed after this exchange.\n"
                f"Current affinity: {affinity}/100\n"
                f"Your current emotion: {agent_emotion_info.get('emotion', '')} — {agent_emotion_info.get('reason', '')}\n"
                "\n"
                "CRITICAL — these Jiho replies are PERSONA VIOLATIONS, not good moves.\n"
                "If Jiho's reply contains ANY of them, delta must be NEGATIVE.\n"
                "A peer-tone direct reply is rewarded; an over-warm / parental / cheerleader reply is punished.\n"
                "  - Excited engagement with status symbols: 'that's wild', 'that's sick', 'camera any good?', asking specs/price about new phones/brands\n"
                "  - Parental tone: 'get some rest', 'go study', 'be careful'\n"
                "  - Cheerleader tone on positive news: 'congrats!!', 'so proud of you', 'what's next for you?'\n"
                "  - Forbidden slang in Jiho's reply: 'ngl', 'fr fr', 'bussin', 'no cap', 'deadass', 'bet', 'on god', 'finna', 'based', 'hits different'\n"
                "  - Accepting / thanking for unprompted trait compliments\n"
                "\n"
                "Output the affinity delta as an integer between -10 and +10, with a brief reason, in JSON.\n"
                'Output format (JSON only): {{"delta": N, "reason": "..."}}'
            )},
            {"role": "user", "content": (
                f"[Recent Chat]\n{recent_str}\n\n"
                f"[Latest Exchange]\nUser: {user_input}\nJiho: {ai_reply}"
            )},
        ],
        max_tokens=100,
        temperature=0,
        response_format={"type": "json_object"},
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        parsed = json.loads(raw)
        delta = max(-10, min(10, int(parsed.get("delta", 0))))
        reason = str(parsed.get("reason", ""))
        return delta, reason
    except Exception:
        return 0, ""

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

# ── Raw Conversation Log (general AI 비교용) ────────────────────────
CONVERSATION_LOG_DIR = "conversations"
_conversation_log_path: str | None = None


def _init_conversation_log() -> None:
    """세션 시작 시 timestamp 기반 로그 파일 생성 + 헤더 기록."""
    global _conversation_log_path
    os.makedirs(CONVERSATION_LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _conversation_log_path = os.path.join(CONVERSATION_LOG_DIR, f"jiho_chat_{stamp}.txt")
    with open(_conversation_log_path, "w", encoding="utf-8") as f:
        f.write("=== Jiho Conversation Log ===\n")
        f.write(f"Session start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Initial affinity: {affinity}\n\n")
    print(f"[Log] 대화 기록: {_conversation_log_path}")


def _log_turn(role: str, text: str) -> None:
    """한 turn을 raw text 로그에 append. role: 'user' or 'ai'."""
    if _conversation_log_path is None:
        return
    label = "User" if role == "user" else "Jiho"
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(_conversation_log_path, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {label}: {text}\n")


# ── JSONL Export for Autorater ──────────────────────────────────────
EXPORT_FILE = "autorater_target.jsonl"

def export_to_jsonl(
    user_input: str,
    ai_reply: str,
    affinity_at_response: int,
    consecutive_neg: int,
    agent_emotion_info: dict | None = None,
) -> None:
    """Append one turn to autorater_target.jsonl in the Learning_Friend_Autorater format.

    affinity_at_response = the affinity score in effect WHEN the AI generated the reply
    (i.e. the pre-update value), so the judge sees the score the response was conditioned on.
    """
    timestamp_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    emotion_str = ""
    if agent_emotion_info:
        emotion_str = f", agent_emotion={agent_emotion_info.get('emotion', '')}"
    record = {
        "id": f"ai_friend_{timestamp_id}",
        "input": user_input,
        "context": f"affinity={affinity_at_response}, consecutive_negative={consecutive_neg}{emotion_str}",
        "messages": [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": ai_reply},
        ],
    }
    with open(EXPORT_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

# ── 실행 ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mode_label = "ON (풀 시스템)" if USE_LONG_TERM_MEMORY else "OFF (페르소나 단독 평가 모드)"
    print(f"\n[모드] 장기기억 RAG: {mode_label}")
    # INITIAL_HISTORY를 단기기억에 시드로 로드 (자연스러운 follow-up용)
    conversation_history.extend(INITIAL_HISTORY)
    print(f"[Seed] 단기기억 {len(INITIAL_HISTORY)}개 로드됨")
    _init_conversation_log()
    print("대화를 시작합니다. 종료하려면 'exit' 입력\n")
    while True:
        user_input = input("유저: ").strip()
        if user_input.lower() == "exit":
            break
        if not user_input:
            continue

        time.sleep(random.uniform(0.5, 1.0))
        print("AI: ...", flush=True)

        start_total = time.time()

        # 호감도에 따라 장기기억 개수 조정
        top_k = 1 if affinity <= 40 else 5

        if USE_LONG_TERM_MEMORY:
            long_term = get_long_term_memory(user_input, top_k)
        else:
            long_term = []

        # 시간대 한 번만 flag되도록 turn 시작 시 한 번 계산해서 양쪽에 동일하게 주입
        time_str_turn, time_ctx_turn = _consume_time_context_for_turn()
        if time_ctx_turn is None:
            print(f"[Time] {time_str_turn} (bucket 재언급 suppress)")
        else:
            print(f"[Time] {time_str_turn} ({time_ctx_turn})")

        # ── 1st call: 감정 + 행동 결정 (한 번에) ─────────────────
        decision = make_decision(user_input, long_term, time_str_turn, time_ctx_turn)
        agent_emotion_info = {
            "emotion": decision.get("emotion", "neutral"),
            "reason":  decision.get("emotion_reason", ""),
        }
        print(f"[Agent 감정] {agent_emotion_info['emotion']} — {agent_emotion_info['reason']}")

        # ── 2nd call: 답변 생성 ──────────────────────────────────
        prompt = build_prompt(
            user_input,
            agent_emotion_info=agent_emotion_info,
            long_term_memories=long_term,
            decision=decision,
            time_str=time_str_turn,
            time_ctx=time_ctx_turn,
        )
        ai_raw = generate_ai_response(prompt)

        if decision.get("timing") == "double_text":
            ai_replies = _split_double_text(ai_raw)
        else:
            ai_replies = [ai_raw]

        ai_reply_joined = " ".join(ai_replies)

        # 히스토리 저장 + raw 로그
        add_to_history("user", user_input)
        _log_turn("user", user_input)
        for msg in ai_replies:
            add_to_history("ai", msg)
            _log_turn("ai", msg)

        # 호감도 업데이트
        with ThreadPoolExecutor() as executor:
            future_affinity = executor.submit(
                update_affinity, agent_emotion_info, user_input, ai_reply_joined
            )
            delta, affinity_reason = future_affinity.result()

        # 장기기억 트리거
        record_turn(user_input, ai_reply_joined, session_break=decision.get("session_break", False))

        # 연속 마이너스 3회부터 ×2 적용
        if delta < 0:
            consecutive_negative += 1
            if consecutive_negative >= 3:
                actual_delta = delta * 2
            else:
                actual_delta = delta
        else:
            consecutive_negative = 0
            actual_delta = delta

        old_affinity = affinity
        affinity = max(0, min(100, affinity + actual_delta))

        # JSONL export
        export_to_jsonl(
            user_input=user_input,
            ai_reply=ai_reply_joined,
            affinity_at_response=old_affinity,
            consecutive_neg=consecutive_negative,
            agent_emotion_info=agent_emotion_info,
        )

        # ── 출력 ─────────────────────────────────────────────────
        for i, msg in enumerate(ai_replies):
            if i > 0:
                time.sleep(random.uniform(0.3, 0.8))
            print(f"\nJiho: {msg}")

        # ── 쿨다운 처리 (wrap_up) ────────────────────────────────
        if decision.get("timing") == "wrap_up":
            cd_min = max(15, min(120, int(decision.get("cooldown_minutes") or 30)))
            _cooldown_until = datetime.now() + timedelta(minutes=cd_min)
            _cooldown_reason = decision.get("wrap_up_reason") or "had to go"
            _last_response_time = datetime.now()
            print(f"[Cooldown] Jiho 자리비움 ~{cd_min}분 ({_cooldown_reason})")
        else:
            _last_response_time = datetime.now()

        multiplier_note = " (×2)" if delta < 0 and consecutive_negative >= 3 else ""
        timing_tag = decision.get("timing", "instant")
        action_tag = decision.get("action", "normal")
        print(f"[호감도] {old_affinity} → {affinity} ({delta:+d}{multiplier_note}) | {affinity_reason}")
        break_tag = decision.get("session_break", False)
        print(f"[행동] timing={timing_tag}, action={action_tag}, session_break={break_tag}")
        print(f"[Export] → {EXPORT_FILE}")
        print(f"[총 레이턴시: {time.time() - start_total:.4f}초]\n")
