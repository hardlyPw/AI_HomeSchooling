"""Jiho 친구 Agent를 FastAPI 서버에서 쓰기 위한 서비스 계층.

Agent/AI_Friend.py는 프롬프트, 장기기억, 호감도, 답변 생성 로직을 들고 있고,
이 파일은 그 로직을 API 응답 형식에 맞게 감싸는 역할을 한다.
프론트(FriendView)는 여기서 yield되는 dict들을 SSE 이벤트로 받아 채팅 UI를 갱신한다.
"""

from __future__ import annotations

import os
import random
import sys
import threading
import time
from pathlib import Path
from typing import Iterator

# Make Agent/AI_Friend.py importable
_AGENT_DIR = Path(__file__).resolve().parents[2] / "Agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

import AI_Friend as af  # noqa: E402

# Server mode: silence the debug prompt dumps that AI_Friend.py prints in CLI
af.DEBUG_PROMPT = False


DELAY_TURN_THRESHOLD = 50
EARLY_AWAY_PROBABILITY = 0.01
LATE_AWAY_PROBABILITY = 0.10
ALWAYS_COOLDOWN_PROBABILITY = 0.001
COOLDOWN_SECONDS = 5 * 60
COOLDOWN_REASONS = (
    "in a game",
    "eating",
    "watching yt",
    "in the shower",
    "looking for my charger",
)


class AwayDecision:
    """Jiho가 이번 턴에 바로 답할지, 늦게 답할지, 자리를 비울지 담는 값 객체."""

    def __init__(self, mode: str = "normal", wait_seconds: int = 0, reason: str = "") -> None:
        """mode는 normal/delayed/cooldown 중 하나로 쓰이고, wait_seconds는 대기 시간이다."""
        self.mode = mode
        self.wait_seconds = wait_seconds
        self.reason = reason


class FriendService:
    """FastAPI의 friend 라우터가 사용하는 Jiho 채팅 서비스.

    주된 역할:
    - Agent/AI_Friend.py의 전역 상태를 서버용으로 초기화/관리한다.
    - 한 턴마다 장기기억 검색, decision layer, 답변 생성, 호감도 갱신을 순서대로 실행한다.
    - 프론트가 바로 처리할 수 있게 delta/decision/affinity/done 이벤트를 yield한다.
    """

    def __init__(self) -> None:
        """서버 시작 시 Jiho의 대화/호감도/쿨다운 상태를 깨끗하게 초기화한다."""
        # Reset AI_Friend module state so each fresh service starts clean.
        af.conversation_history.clear()
        af.affinity = 70
        af.consecutive_negative = 0
        af._cooldown_until = None
        af._cooldown_reason = ""
        self._away_count = 0
        self._force_next_cooldown = False
        self._force_next_double_text = False
        self._cooldown_skip_event = threading.Event()

    # ── State exposed to api/v1/friend.py ─────────────────────────────
    @property
    def affinity(self) -> int:
        """현재 Jiho 호감도(0~100)를 API 응답용으로 노출한다."""
        return af.affinity

    @property
    def history(self) -> list[dict]:
        """현재 서버 메모리에 쌓인 단기 대화 기록을 API 응답용으로 노출한다."""
        return af.conversation_history

    def reset(self) -> None:
        """디버그/데모용 전체 초기화.

        프론트의 reset 버튼에서 호출된다. 단기기억, 호감도, 쿨다운, 강제 이벤트 플래그를
        초기화하고, 가능하면 Supabase의 데모 장기기억도 기본값으로 되돌린다.
        """
        af.conversation_history.clear()
        af.affinity = 70
        af.consecutive_negative = 0
        af._cooldown_until = None
        af._cooldown_reason = ""
        self._away_count = 0
        self._force_next_cooldown = False
        self._force_next_double_text = False
        self._cooldown_skip_event.clear()
        drain_pending = getattr(af, "_drain_pending_chunk", None)
        if callable(drain_pending):
            drain_pending()
        self._reset_long_term_memory_for_demo()

    def _reset_long_term_memory_for_demo(self) -> None:
        """Supabase RPC가 있을 때 데모용 장기기억 테이블을 초기 상태로 되돌린다."""
        try:
            af.supabase.rpc("reset_friend_memories_v2_to_demo_seed", {}).execute()
        except Exception as exc:
            print(f"[FriendService] demo DB reset skipped: {exc!s:.200s}")

    def force_next_cooldown(self) -> None:
        """다음 사용자 메시지에서 Jiho가 강제로 cooldown 상태에 들어가게 예약한다."""
        self._force_next_cooldown = True

    def force_next_double_text(self) -> None:
        """다음 사용자 메시지에서 Jiho가 강제로 두 번 나눠 답장하게 예약한다."""
        self._force_next_double_text = True

    def end_cooldown(self) -> None:
        """진행 중인 cooldown 대기를 즉시 끝낸다. 디버그 UI의 cooldown_end 버튼용이다."""
        self._cooldown_skip_event.set()

    def _apply_delta(self, delta: int) -> int:
        """decision layer가 판단한 호감도 변화량을 실제 호감도에 반영한다.

        반환값은 변경 전 호감도다. 연속으로 부정적인 delta가 나오면 더 크게 깎이도록
        consecutive_negative를 관리하고, 최종 호감도는 0~100 사이로 제한한다.
        """
        if delta < 0:
            af.consecutive_negative += 1
            if af.consecutive_negative >= 3:
                delta *= 2
        else:
            af.consecutive_negative = 0
        old = af.affinity
        af.affinity = max(0, min(100, af.affinity + delta))
        return old

    def _pick_away_decision(self) -> AwayDecision:
        """이번 턴에서 Jiho의 응답 타이밍을 결정한다.

        반환 모드:
        - normal: 바로 답장
        - delayed: 30~60초 늦게 답장하는 척함
        - cooldown: 몇 분 동안 자리를 비운 뒤 답장

        대화가 길어질수록 away 확률이 올라가고, 디버그 플래그가 있으면 강제로 cooldown을 만든다.
        """
        if self._force_next_cooldown:
            self._force_next_cooldown = False
            return self._begin_cooldown()

        if random.random() < ALWAYS_COOLDOWN_PROBABILITY:
            return self._begin_cooldown()

        turn_count = len(af.conversation_history) // 2
        away_probability = (
            EARLY_AWAY_PROBABILITY
            if turn_count < DELAY_TURN_THRESHOLD
            else LATE_AWAY_PROBABILITY
        )
        if random.random() >= away_probability:
            return AwayDecision()

        self._away_count += 1
        if self._away_count <= 3:
            return AwayDecision(mode="delayed", wait_seconds=30)
        if self._away_count == 4:
            return AwayDecision(mode="delayed", wait_seconds=60)
        return self._begin_cooldown()

    def _begin_cooldown(self) -> AwayDecision:
        """cooldown AwayDecision을 만든다. reason은 답장 prefix에만 쓰인다."""
        self._away_count += 1
        return AwayDecision(
            mode="cooldown",
            wait_seconds=COOLDOWN_SECONDS,
            reason=random.choice(COOLDOWN_REASONS),
        )

    # ── Streaming reply ──────────────────────────────────────────────
    def stream_reply(self, user_message: str) -> Iterator[dict]:
        """사용자 메시지 하나에 대한 Jiho 답변 전체 파이프라인을 실행한다.

        실행 순서:
        1. delayed/cooldown 같은 자리비움 이벤트를 먼저 결정한다.
        2. Supabase 장기기억에서 현재 메시지와 관련된 기억을 검색한다.
        3. decision layer로 Jiho의 감정, 답장 타이밍, 행동, 호감도 변화를 판단한다.
        4. 호감도를 갱신하고 decision 정보를 프론트 디버그 패널에 보낸다.
        5. persona + 장기기억 + 단기기억 + decision cue를 합쳐 최종 프롬프트를 만든다.
        6. GPT 답변을 스트리밍하거나 double-text일 때는 두 메시지로 나눠 보낸다.
        7. 단기기억/장기기억 후보에 이번 턴을 기록하고 timing/tokens/affinity/done을 보낸다.

        yield되는 dict는 friend.py에서 SSE data 이벤트로 직렬화된다.
        """
        turn_started = time.perf_counter()
        away = self._pick_away_decision()

        if away.mode in {"delayed", "cooldown"}:
            # 프론트는 status 이벤트를 보고 typing/offline 상태를 먼저 바꾼다.
            yield {"status": away.mode, "wait_seconds": away.wait_seconds}
            if away.mode == "cooldown":
                self._cooldown_skip_event.wait(timeout=away.wait_seconds)
                self._cooldown_skip_event.clear()
            else:
                time.sleep(away.wait_seconds)

        # Long-term RAG retrieval (top_k uses CURRENT affinity, before LLM delta)
        top_k = 1 if af.affinity <= 40 else 5
        if af.USE_LONG_TERM_MEMORY:
            long_term = af.get_long_term_memory(user_message, top_k=top_k)
        else:
            long_term = []

        # Decision Layer (gpt-4o-mini): emotion + timing + action + session_break + affinity_delta
        time_str, time_ctx = af._consume_time_context_for_turn()
        decision = af.make_decision(user_message, long_term, time_str, time_ctx)
        if self._force_next_double_text:
            self._force_next_double_text = False
            decision = dict(decision)
            decision["timing"] = "double_text"
        agent_emo = {
            "emotion": decision.get("emotion", ""),
            "reason": decision.get("emotion_reason", ""),
        }

        # Apply LLM-judged affinity delta from the decision layer (replaces keyword stub)
        aff_delta = int(decision.get("affinity_delta", 0))
        old_affinity = self._apply_delta(aff_delta)
        actual_change = af.affinity - old_affinity
        print(
            f"[호감도] {old_affinity} → {af.affinity} "
            f"({actual_change:+d}) | {decision.get('affinity_reason', '')}"
        )

        # 디버그 패널에서 emotion/timing/action/affinity 변화를 보여주기 위한 이벤트.
        yield {
            "decision": {
                "user_message": user_message,
                "emotion": decision.get("emotion", ""),
                "emotion_reason": decision.get("emotion_reason", ""),
                "timing": decision.get("timing", ""),
                "action": decision.get("action", ""),
                "affinity_prev": old_affinity,
                "affinity_next": af.affinity,
                "affinity_delta": actual_change,
                "affinity_reason": decision.get("affinity_reason", ""),
                "reasoning": decision.get("reasoning", ""),
                "away_mode": away.mode,
            }
        }

        # Build prompt with full persona + RAG + STM + decision cues + emotion
        prompt = af.build_prompt(
            user_input=user_message,
            long_term_memories=long_term,
            long_term_k=top_k,
            decision=decision,
            agent_emotion_info=agent_emo,
            time_str=time_str,
            time_ctx=time_ctx,
        )

        # Stream reply (AI_Friend.generate_ai_response is non-streaming, so we
        # call the openai client directly with stream=True here)
        llm_started = time.perf_counter()
        collected: list[str] = []
        first_delta_seconds: float | None = None
        if away.mode == "cooldown":
            # cooldown 뒤 돌아왔다는 느낌을 주기 위해 첫 말 앞에 짧은 excuse를 붙인다.
            prefix = f"yo sry was {away.reason}."
            collected.append(prefix)
            yield {"delta": prefix}
            yield {"message_break": True}

        reply_prompt_tokens: int | None = None
        reply_completion_tokens: int | None = None

        if decision.get("timing") == "double_text":
            # double_text는 실제 스트리밍 대신 한 번 생성한 답변을 두 말풍선으로 나눠 보낸다.
            ai_raw = af.generate_ai_response(prompt)
            ai_replies = af._split_double_text(ai_raw)
            for idx, msg in enumerate(ai_replies):
                if idx > 0:
                    yield {"message_break": True}
                if first_delta_seconds is None:
                    first_delta_seconds = time.perf_counter() - llm_started
                collected.append((" " if collected else "") + msg)
                yield {"delta": msg}
            usage = getattr(af, "last_response_usage", None)
            if usage:
                reply_prompt_tokens = usage.get("prompt_tokens")
                reply_completion_tokens = usage.get("completion_tokens")
        else:
            # 일반 답변은 GPT stream=True를 사용해서 토큰 단위 delta를 프론트로 보낸다.
            stream = af.openai_client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "system", "content": prompt}],
                temperature=0.8,
                max_tokens=300,
                stream=True,
                stream_options={"include_usage": True},
            )

            for chunk in stream:
                if getattr(chunk, "usage", None) is not None:
                    reply_prompt_tokens = chunk.usage.prompt_tokens
                    reply_completion_tokens = chunk.usage.completion_tokens
                if not chunk.choices:
                    continue
                piece = chunk.choices[0].delta.content
                if piece:
                    if first_delta_seconds is None:
                        first_delta_seconds = time.perf_counter() - llm_started
                    collected.append(piece)
                    yield {"delta": piece}
            print(f"[Latency] GPT 답변: {time.perf_counter() - llm_started:.4f}초")

        reply = "".join(collected).strip() or "brb"

        # Short-term memory: append both sides for next turn's context
        af.conversation_history.append({"role": "user", "text": user_message})
        af.conversation_history.append({"role": "ai",   "text": reply})

        # Long-term memory: feed into the chunk consolidator (5-min idle or
        # session_break triggers the gpt-4o-mini extraction → friend_memories_v2)
        try:
            af.record_turn(
                user_message,
                reply,
                session_break=bool(decision.get("session_break", False)),
            )
        except Exception as exc:
            print(f"[FriendService] record_turn failed: {exc!s:.200s}")

        total_seconds = time.perf_counter() - turn_started
        llm_seconds = time.perf_counter() - llm_started
        first_delta_text = (
            f"{first_delta_seconds:.2f}s"
            if first_delta_seconds is not None
            else "n/a"
        )
        print(
            "[FriendService] response_time "
            f"total={total_seconds:.2f}s "
            f"llm_stream={llm_seconds:.2f}s "
            f"first_delta={first_delta_text} "
            f"mode={away.mode} "
            f"wait={away.wait_seconds}s "
            f"user_chars={len(user_message)} "
            f"reply_chars={len(reply)}"
        )

        # 여기부터는 실제 답변 내용이 아니라 프론트 디버그/상태 갱신용 마무리 이벤트들이다.
        yield {"timing": {"total_seconds": round(total_seconds, 2)}}

        decision_usage = decision.get("_usage") or {}
        decision_prompt = decision_usage.get("prompt_tokens")
        decision_completion = decision_usage.get("completion_tokens")
        token_components = [
            (decision_prompt or 0) + (decision_completion or 0),
            (reply_prompt_tokens or 0) + (reply_completion_tokens or 0),
        ]
        yield {
            "tokens": {
                "decision_prompt": decision_prompt,
                "decision_completion": decision_completion,
                "reply_prompt": reply_prompt_tokens,
                "reply_completion": reply_completion_tokens,
                "total": sum(token_components) if any(token_components) else None,
            }
        }
        yield {"affinity": af.affinity, "affinity_prev": old_affinity}
        yield {"done": True}
