from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import time

from jiho_decision_prompt import render_jiho_decision_prompt


VALID_TIMINGS = {"instant", "delayed", "double_text", "wrap_up"}
VALID_ACTIONS = {"normal", "topic_drift", "memory_flashback"}


@dataclass(frozen=True)
class DecisionResult:
    decision: dict
    cooldown_until: datetime | None
    cooldown_reason: str


def make_decision(
    *,
    openai_client,
    user_input: str,
    long_term_memories: list[dict],
    time_str: str,
    time_ctx: str | None,
    affinity: int,
    conversation_history: list[dict],
    cooldown_until: datetime | None,
    cooldown_reason: str,
    last_response_time: datetime,
) -> DecisionResult:
    """Run Jiho's decision layer and normalize the result."""

    came_back_from = None
    next_cooldown_until = cooldown_until
    next_cooldown_reason = cooldown_reason
    if cooldown_until is not None:
        mins_away = max(1, int((cooldown_until - last_response_time).total_seconds() / 60))
        came_back_from = f"away ~{mins_away} min ({cooldown_reason})"
        next_cooldown_until = None
        next_cooldown_reason = ""

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
        response = openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}],
            max_tokens=200,
            temperature=0.6,
            response_format={"type": "json_object"},
        )
        raw = (response.choices[0].message.content or "").strip()
        decision = json.loads(raw)
        if getattr(response, "usage", None) is not None:
            decision["_usage"] = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
            }
        print(
            f"[Decision] {time.time() - start:.2f}s -> "
            f"timing={decision.get('timing')}, action={decision.get('action')}, "
            f"break={decision.get('session_break')}, "
            f"aff_delta={decision.get('affinity_delta', 0)}, "
            f"reason={decision.get('reasoning', '')}"
        )
    except Exception as exc:
        print(f"[Decision] failed, fallback: {exc}")
        decision = {
            "timing": "instant",
            "action": "normal",
            "session_break": False,
            "reasoning": "fallback",
        }

    normalized = normalize_decision(decision, came_back_from=came_back_from)
    return DecisionResult(
        decision=normalized,
        cooldown_until=next_cooldown_until,
        cooldown_reason=next_cooldown_reason,
    )


def normalize_decision(decision: dict, *, came_back_from: str | None = None) -> dict:
    if decision.get("timing") not in VALID_TIMINGS:
        decision["timing"] = "instant"
    if decision.get("action") not in VALID_ACTIONS:
        decision["action"] = "normal"

    decision["session_break"] = bool(decision.get("session_break", False))
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
