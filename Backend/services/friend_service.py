"""Stub Jiho-persona chat service for the Friend mode.

This is intentionally lightweight — it does NOT yet integrate Agent/AI_Friend.py
(which carries long-term memory, embedding models, etc.). It exposes the same
streaming surface as ChatService, plus an affinity score that updates per turn.
"""
from __future__ import annotations

import os
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

_openai = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

HISTORY_LIMIT = 60

JIHO_PERSONA = """You are Jiho, a 14-year-old Korean-American 8th grader in
California. You are texting a friend on a messaging app. You are NOT a teacher,
NOT a tutor, NOT a therapist.

Voice & style (texting, not prose):
- All lowercase unless it's a proper noun. Short. 1–2 sentences per message, often less.
- Casual middle-school internet slang is fine in moderation: "ngl", "fr", "lol",
  "idk", "bruh", "lmao". Do not overuse — sprinkle, don't pile.
- No emojis. No formal punctuation (no semicolons, no em-dashes).
- Never explain English grammar, never correct the other person's English,
  never act like a teacher. You're just a friend texting back.
- Reply to what they said, then maybe ask one short follow-up. Don't dump.

Affinity rules (you receive a current affinity value 0–100 from the system):
- 0–30 (low): cold, very short, one-word or "k" / "idk" / "later". Bored,
  done with the conversation. Do not console, do not give advice.
- 31–60 (mid): polite but flat. Short replies, minimal warmth.
- 61–85 (good): friendly, comfortable, jokes a little.
- 86–100 (high): warm, playful, teases lightly, shows you care without being mushy.

Never break character. Never mention that you are an AI or a language model.
"""


# Simple keyword-based affinity nudges. Real AI_Friend.py uses a model call;
# this stub is just "alive enough" for the UI to demo expression changes.
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
        self.history: list[dict] = []
        self.affinity: int = 70  # mirrors AI_Friend.py default
        self.consecutive_negative: int = 0

    def _affinity_delta(self, user_text: str) -> int:
        t = user_text.lower()
        delta = 0
        if any(h in t for h in POSITIVE_HINTS):
            delta += 4
        if any(h in t for h in NEGATIVE_HINTS):
            delta -= 6
        # Bare "k" / "idk" / "whatever" hurts a little.
        stripped = t.strip().strip(".!?")
        if stripped in {"k", "ok", "idk", "whatever", "meh"}:
            delta -= 2
        return delta

    def _apply_delta(self, delta: int) -> int:
        if delta < 0:
            self.consecutive_negative += 1
            if self.consecutive_negative >= 3:
                delta *= 2
        else:
            self.consecutive_negative = 0
        old = self.affinity
        self.affinity = max(0, min(100, self.affinity + delta))
        return old

    def reset(self) -> None:
        self.history.clear()
        self.affinity = 70
        self.consecutive_negative = 0

    def stream_reply(self, user_message: str) -> Iterator[dict]:
        """Yields {"delta": str} chunks, then {"affinity": int}, then {"done": True}."""
        old_affinity = self._apply_delta(self._affinity_delta(user_message))

        system_prompt = (
            JIHO_PERSONA
            + f"\n\n[Current affinity toward this person: {self.affinity}/100]"
        )
        messages: list[dict] = [{"role": "system", "content": system_prompt}]
        for m in self.history[-HISTORY_LIMIT:]:
            messages.append({"role": m["role"], "content": m["text"]})
        messages.append({"role": "user", "content": user_message})

        stream = _openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.9,
            max_tokens=200,
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

        reply = "".join(collected).strip() or "..."
        self.history.append({"role": "user", "text": user_message})
        self.history.append({"role": "assistant", "text": reply})
        if len(self.history) > HISTORY_LIMIT * 2:
            self.history = self.history[-HISTORY_LIMIT * 2:]

        yield {"affinity": self.affinity, "affinity_prev": old_affinity}
        yield {"done": True}
