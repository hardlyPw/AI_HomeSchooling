"""Jiho friend chat service — wraps Agent/AI_Friend.py for the FastAPI app.

friend_service.py was previously a lightweight stub (keyword affinity, no RAG).
Now it delegates to the real Agent/AI_Friend.py so the web UI gets the same
persona, long-term memory retrieval (friend_memories_v2), and chunk
consolidation as the standalone CLI.

State note: AI_Friend.py uses module-level globals (conversation_history,
affinity, _pending_chunk). This service is a process-singleton, so for a
single-user demo this is fine. Multi-user would require refactoring AI_Friend
to per-session state.
"""
from __future__ import annotations

import os
import random
import sys
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


# Lightweight keyword affinity nudges (kept from stub — AI_Friend's decision
# layer is heavier and adds a second API call per turn; can be reintroduced
# later if we want the full system).
POSITIVE_HINTS = (
    "thanks", "thank you", "love", "miss you", "lol", "haha", "lmao",
    "u r the best", "ur the best", "you're the best", "fr",
    "appreciate", "ngl ur cool", "ily",
)
NEGATIVE_HINTS = (
    "shut up", "stfu", "stupid", "annoying", "boring", "lame",
    "i hate", "hate you", "leave me alone", "idc", "whatever",
    "kys", "fuck you", "fk u", "trash",
)

DELAY_TURN_THRESHOLD = 50
EARLY_AWAY_PROBABILITY = 0.01
LATE_AWAY_PROBABILITY = 0.10
ALWAYS_COOLDOWN_PROBABILITY = 0.001
COOLDOWN_SECONDS = 5 * 60
COOLDOWN_REASONS = (
    "게임 한 판 하느라",
    "밥 먹느라",
    "유튜브 보느라",
    "잠깐 씻느라",
    "폰 충전기 찾느라",
)


class AwayDecision:
    def __init__(self, mode: str = "normal", wait_seconds: int = 0, reason: str = "") -> None:
        self.mode = mode
        self.wait_seconds = wait_seconds
        self.reason = reason


class FriendService:
    def __init__(self) -> None:
        # Reset AI_Friend module state so each fresh service starts clean.
        af.conversation_history.clear()
        af.affinity = 70
        af.consecutive_negative = 0
        af._cooldown_until = None
        af._cooldown_reason = ""
        self._away_count = 0
        self._force_next_cooldown = False

    # ── State exposed to api/v1/friend.py ─────────────────────────────
    @property
    def affinity(self) -> int:
        return af.affinity

    @property
    def history(self) -> list[dict]:
        return af.conversation_history

    def reset(self) -> None:
        af.conversation_history.clear()
        af.affinity = 70
        af.consecutive_negative = 0
        af._cooldown_until = None
        af._cooldown_reason = ""
        self._away_count = 0
        self._force_next_cooldown = False
        drain_pending = getattr(af, "_drain_pending_chunk", None)
        if callable(drain_pending):
            drain_pending()
        self._reset_long_term_memory_for_demo()

    def _reset_long_term_memory_for_demo(self) -> None:
        """Restore the demo long-term memory baseline when the Supabase RPC exists."""
        try:
            af.supabase.rpc("reset_friend_memories_v2_to_demo_seed", {}).execute()
        except Exception as exc:
            print(f"[FriendService] demo DB reset skipped: {exc!s:.200s}")

    def force_next_cooldown(self) -> None:
        self._force_next_cooldown = True

    # ── Affinity update (keyword stub) ────────────────────────────────
    def _affinity_delta(self, user_text: str) -> int:
        t = user_text.lower()
        delta = 0
        if any(h in t for h in POSITIVE_HINTS):
            delta += 4
        if any(h in t for h in NEGATIVE_HINTS):
            delta -= 6
        stripped = t.strip().strip(".!?")
        if stripped in {"k", "ok", "idk", "whatever", "meh"}:
            delta -= 2
        return delta

    def _apply_delta(self, delta: int) -> int:
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
        self._away_count += 1
        return AwayDecision(
            mode="cooldown",
            wait_seconds=COOLDOWN_SECONDS,
            reason=random.choice(COOLDOWN_REASONS),
        )

    # ── Streaming reply ──────────────────────────────────────────────
    def stream_reply(self, user_message: str) -> Iterator[dict]:
        """Yields {"delta": str} chunks, then affinity, then done."""
        turn_started = time.perf_counter()
        old_affinity = self._apply_delta(self._affinity_delta(user_message))
        away = self._pick_away_decision()

        if away.mode in {"delayed", "cooldown"}:
            yield {"status": away.mode, "wait_seconds": away.wait_seconds}
            time.sleep(away.wait_seconds)

        # Long-term RAG retrieval (mirrors AI_Friend.py main loop)
        top_k = 1 if af.affinity <= 40 else 5
        if af.USE_LONG_TERM_MEMORY:
            long_term = af.get_long_term_memory(user_message, top_k=top_k)
        else:
            long_term = []

        # Decision Layer (gpt-4o-mini): emotion + timing + action + session_break
        time_str, time_ctx = af._consume_time_context_for_turn()
        decision = af.make_decision(user_message, long_term, time_str, time_ctx)
        agent_emo = {
            "emotion": decision.get("emotion", ""),
            "reason": decision.get("emotion_reason", ""),
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
        stream = af.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
            stream=True,
        )

        collected: list[str] = []
        first_delta_seconds: float | None = None
        if away.mode == "cooldown":
            prefix = f"나 {away.reason} 잠깐 갔다 왔어. "
            collected.append(prefix)
            yield {"delta": prefix}

        for chunk in stream:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if piece:
                if first_delta_seconds is None:
                    first_delta_seconds = time.perf_counter() - llm_started
                collected.append(piece)
                yield {"delta": piece}

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

        yield {"affinity": af.affinity, "affinity_prev": old_affinity}
        yield {"done": True}
