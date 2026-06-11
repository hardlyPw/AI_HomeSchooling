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
import sys
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


class FriendService:
    def __init__(self) -> None:
        # Reset AI_Friend module state so each fresh service starts clean.
        af.conversation_history.clear()
        af.affinity = 70
        af.consecutive_negative = 0

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

    # ── Streaming reply ──────────────────────────────────────────────
    def stream_reply(self, user_message: str) -> Iterator[dict]:
        """Yields {"delta": str} chunks, then affinity, then done."""
        old_affinity = self._apply_delta(self._affinity_delta(user_message))

        # Long-term RAG retrieval (mirrors AI_Friend.py main loop)
        top_k = 1 if af.affinity <= 40 else 5
        if af.USE_LONG_TERM_MEMORY:
            long_term = af.get_long_term_memory(user_message, top_k=top_k)
        else:
            long_term = []

        # Build prompt via AI_Friend.build_prompt (full persona + RAG + STM)
        prompt = af.build_prompt(
            user_input=user_message,
            long_term_memories=long_term,
            long_term_k=top_k,
        )

        # Stream reply (AI_Friend.generate_ai_response is non-streaming, so we
        # call the openai client directly with stream=True here)
        stream = af.openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.8,
            max_tokens=300,
            stream=True,
        )

        collected: list[str] = []
        for chunk in stream:
            if not chunk.choices:
                continue
            piece = chunk.choices[0].delta.content
            if piece:
                collected.append(piece)
                yield {"delta": piece}

        reply = "".join(collected).strip() or "brb"

        # Short-term memory: append both sides for next turn's context
        af.conversation_history.append({"role": "user", "text": user_message})
        af.conversation_history.append({"role": "ai",   "text": reply})

        # Long-term memory: feed into the chunk consolidator (5-min idle or
        # session_break triggers the gpt-4o-mini extraction → friend_memories_v2)
        try:
            af.record_turn(user_message, reply, session_break=False)
        except Exception as exc:
            print(f"[FriendService] record_turn failed: {exc!s:.200s}")

        yield {"affinity": af.affinity, "affinity_prev": old_affinity}
        yield {"done": True}
