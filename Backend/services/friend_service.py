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
        self._force_next_double_text = False
        self._cooldown_skip_event = threading.Event()

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
        self._force_next_double_text = False
        self._cooldown_skip_event.clear()
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

    def force_next_double_text(self) -> None:
        self._force_next_double_text = True

    def end_cooldown(self) -> None:
        """Wake up any in-progress cooldown sleep immediately."""
        self._cooldown_skip_event.set()

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
        away = self._pick_away_decision()

        if away.mode in {"delayed", "cooldown"}:
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
            prefix = f"yo sry was {away.reason}."
            collected.append(prefix)
            yield {"delta": prefix}
            yield {"message_break": True}

        reply_prompt_tokens: int | None = None
        reply_completion_tokens: int | None = None

        if decision.get("timing") == "double_text":
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
