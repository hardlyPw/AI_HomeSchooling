from __future__ import annotations

import json
from datetime import datetime


EXPORT_FILE = "autorater_target.jsonl"


def update_affinity(
    *,
    openai_client,
    role_display: dict[str, str],
    conversation_history: list[dict],
    current_affinity: int,
    agent_emotion_info: dict,
    user_input: str,
    ai_reply: str,
) -> tuple[int, str]:
    """Evaluate affinity change for CLI/scenario runs."""

    recent_str = "\n".join(
        f"{role_display.get(message['role'], message['role'])}: {message['text']}"
        for message in conversation_history[-6:]
    )
    response = openai_client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are Jiho, a 7th-grade middle schooler. Direct, dry, peer-tone — NOT a counselor or therapist.\n"
                    "You dislike fakeness, self-pity, repeated whining, status-symbol bragging, and unprompted flattery.\n"
                    "Judge how much your affinity toward the other person changed after this exchange.\n"
                    f"Current affinity: {current_affinity}/100\n"
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
                    'Output format (JSON only): {"delta": N, "reason": "..."}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"[Recent Chat]\n{recent_str}\n\n"
                    f"[Latest Exchange]\nUser: {user_input}\nJiho: {ai_reply}"
                ),
            },
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


def export_to_jsonl(
    user_input: str,
    ai_reply: str,
    affinity_at_response: int,
    consecutive_neg: int,
    agent_emotion_info: dict | None = None,
    export_file: str = EXPORT_FILE,
) -> None:
    """Append one turn to autorater_target.jsonl in the Learning_Friend_Autorater format."""

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
    with open(export_file, "a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
