from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1] / "Backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from domain.agents.jiho import JIHO_DEFINITION  # noqa: E402

ROLE_DISPLAY = {"user": "User", "ai": JIHO_DEFINITION.profile.display_name}
AI_PERSONA = JIHO_DEFINITION.profile.persona.narrative
USER_PROFILE = JIHO_DEFINITION.profile.persona.user_profile


def render_history(messages: list[dict], limit: int) -> str:
    return "\n".join(
        f"{ROLE_DISPLAY.get(m['role'], m['role'])}: {m['text']}"
        for m in messages[-limit:]
    )


def render_long_term_memory(long_term_memories: list[dict]) -> str:
    return "\n".join(
        f"[과거기억] {memory['description']}" for memory in long_term_memories
    ) or "관련 기억 없음"


def render_affinity_state(affinity: int) -> str:
    maxima = JIHO_DEFINITION.runtime.prompt.affinity_stage_maxima
    directions = JIHO_DEFINITION.profile.persona.affinity_stage_directions
    labels = ("Low", "Low-Mid", "Cool", "High")
    stage = next(
        (index for index, maximum in enumerate(maxima) if affinity <= maximum),
        3,
    )
    return (
        f"\n[Current State — {labels[stage]} Affinity: {affinity}/100]\n"
        f"{directions[stage]}\n"
    )


def render_emotion(agent_emotion_info: dict | None) -> str:
    if not agent_emotion_info:
        return ""
    return (
        f"\n[Your Current Emotion]\n"
        f"Emotion: {agent_emotion_info.get('emotion', '')}\n"
        f"Reason: {agent_emotion_info.get('reason', '')}\n"
    )


def render_time_line(time_str: str | None, time_ctx: str | None) -> str:
    if not time_str or not time_ctx:
        return ""
    return f"\n[Current Time]\n{time_str} ({time_ctx})\n"


def render_behavioral_cues(decision: dict | None) -> str:
    if not decision:
        return ""

    cues: list[str] = []
    timing = decision.get("timing", "instant")
    action = decision.get("action", "normal")

    if decision.get("came_back_from"):
        cues.append(
            f"You just came back from being away ({decision['came_back_from']}). "
            "Acknowledge it briefly — 'back' or 'yo im back' — before responding."
        )
    if timing == "delayed":
        excuse = decision.get("delayed_excuse") or "was busy"
        cues.append(f"You were briefly distracted. Open with a quick excuse (e.g. '{excuse}') then respond.")
    elif timing == "wrap_up":
        reason = decision.get("wrap_up_reason") or "gotta go"
        cues.append(f"You need to leave soon. Reason: {reason}. Respond briefly, then say bye naturally.")
    elif timing == "double_text":
        cues.append(
            "Double-text means TWO SHORT separate beats, NOT one long message split in half. "
            "Each beat stays under 8 words. "
            "First beat = quick reaction (e.g. 'no way'). "
            "Second beat = follow-up thought or question (e.g. 'what happened'). "
            "Write the two beats as ONE flowing message separated by a period. "
            "Do NOT use slashes, brackets, or any literal separator in your output. "
            "Stay restrained — no gushing, no 'congrats dude i'm so excited for you'."
        )

    if action == "topic_drift":
        topic = decision.get("drift_topic") or "something on your mind"
        cues.append(f"You want to change the subject to: {topic}. Reply briefly first, then pivot.")
    elif action == "memory_flashback":
        memory_ref = decision.get("memory_ref") or ""
        if memory_ref:
            cues.append(f"This reminds you of: {memory_ref}. Bring it up naturally like 'yo that reminds me...'.")

    if not cues:
        return ""
    return "\n[Behavioral Cues — follow these]\n" + "\n".join(f"- {cue}" for cue in cues) + "\n"


def render_concision_rule(affinity: int) -> str:
    maxima = JIHO_DEFINITION.runtime.prompt.affinity_stage_maxima
    directions = JIHO_DEFINITION.profile.persona.affinity_stage_directions
    stage = next(
        (index for index, maximum in enumerate(maxima) if affinity <= maximum),
        3,
    )
    return directions[stage]


def render_system_safety_rules() -> str:
    rules = JIHO_DEFINITION.runtime.system_safety_rules
    return "\n".join(f"- {rule}" for rule in rules)


def render_behavior_bans() -> str:
    bans = JIHO_DEFINITION.profile.persona.behavior_bans
    return "\n".join(f"- {ban}" for ban in bans)


def render_jiho_prompt(
    *,
    user_input: str,
    affinity: int,
    long_term_memories: list[dict],
    long_term_k: int,
    conversation_history: list[dict],
    agent_emotion_info: dict | None = None,
    decision: dict | None = None,
    time_str: str | None = None,
    time_ctx: str | None = None,
) -> str:
    long_term_str = render_long_term_memory(long_term_memories)
    short_term_str = render_history(
        conversation_history,
        limit=JIHO_DEFINITION.runtime.prompt.response_history_limit,
    ) or "최근 대화 없음"
    affinity_str = render_affinity_state(affinity)
    agent_emo_str = render_emotion(agent_emotion_info)
    time_line = render_time_line(time_str, time_ctx)
    decision_str = render_behavioral_cues(decision)
    concision_rule = render_concision_rule(affinity)
    safety_rules = render_system_safety_rules()
    behavior_bans = render_behavior_bans()

    return f"""[Persona]
{AI_PERSONA}
{affinity_str}
[User Profile]
{USER_PROFILE}

[Long-term Memory — Top {long_term_k} Relevant Memories]
{long_term_str}

[Short-term Memory — Recent Conversation]
{short_term_str}
{agent_emo_str}{time_line}{decision_str}
[Current User Input]
{user_input}

[Instructions]
0. Fixed system safety rules:
{safety_rules}
1. Memory usage:
   - If [Long-term Memory] contains something specifically relevant and worth referencing, weave it in naturally.
   - If memory has nothing relevant, do NOT fabricate. React naturally as Jiho would.
2. Conversation flow:
   - Always continue from [Short-term Memory]. Never act like the conversation just started.
3. Speech constraints:
   - Casual American 7th-grader English ONLY. No textbook tone, no polite formality, no Korean.
   - {concision_rule}
4. Emotional reflection:
   - Anchor your response in [Your Current Emotion]. You're a 7th grader whose mood shows easily.
5. Behavioral cues:
   - If [Behavioral Cues] is present, follow those instructions naturally.
   - Time awareness: if it's late, meal time, or school hours, let it show in your response.

[BANNED MOVES — pre-flight check]
Scan your draft. If any appear, rewrite — they break peer-tone:

{behavior_bans}
"""
