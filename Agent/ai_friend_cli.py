from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import random
import time
from types import ModuleType


_conversation_log_path: str | None = None
CONVERSATION_LOG_DIR = "conversations"


def _init_conversation_log(af: ModuleType) -> None:
    global _conversation_log_path
    import os

    os.makedirs(CONVERSATION_LOG_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _conversation_log_path = os.path.join(CONVERSATION_LOG_DIR, f"jiho_chat_{stamp}.txt")
    with open(_conversation_log_path, "w", encoding="utf-8") as file:
        file.write("=== Jiho Conversation Log ===\n")
        file.write(f"Session start: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        file.write(f"Initial affinity: {af.affinity}\n\n")
    print(f"[Log] 대화 기록: {_conversation_log_path}")


def _log_turn(role: str, text: str) -> None:
    if _conversation_log_path is None:
        return
    label = "User" if role == "user" else "Jiho"
    timestamp = datetime.now().strftime("%H:%M:%S")
    with open(_conversation_log_path, "a", encoding="utf-8") as file:
        file.write(f"[{timestamp}] {label}: {text}\n")


def main(af_module: ModuleType | None = None) -> None:
    if af_module is None:
        import AI_Friend as af
    else:
        af = af_module

    mode_label = "ON (풀 시스템)" if af.USE_LONG_TERM_MEMORY else "OFF (페르소나 단독 평가 모드)"
    print(f"\n[모드] 장기기억 RAG: {mode_label}")
    af.conversation_history.extend(af.INITIAL_HISTORY)
    print(f"[Seed] 단기기억 {len(af.INITIAL_HISTORY)}개 로드됨")
    _init_conversation_log(af)
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
        top_k = 1 if af.affinity <= 40 else 5

        if af.USE_LONG_TERM_MEMORY:
            long_term = af.get_long_term_memory(user_input, top_k)
        else:
            long_term = []

        time_str_turn, time_ctx_turn = af._consume_time_context_for_turn()
        if time_ctx_turn is None:
            print(f"[Time] {time_str_turn} (bucket 재언급 suppress)")
        else:
            print(f"[Time] {time_str_turn} ({time_ctx_turn})")

        decision = af.make_decision(user_input, long_term, time_str_turn, time_ctx_turn)
        agent_emotion_info = {
            "emotion": decision.get("emotion", "neutral"),
            "reason": decision.get("emotion_reason", ""),
        }
        print(f"[Agent 감정] {agent_emotion_info['emotion']} — {agent_emotion_info['reason']}")

        prompt = af.build_prompt(
            user_input,
            agent_emotion_info=agent_emotion_info,
            long_term_memories=long_term,
            decision=decision,
            time_str=time_str_turn,
            time_ctx=time_ctx_turn,
        )
        ai_raw = af.generate_ai_response(prompt)
        if decision.get("timing") == "double_text":
            ai_replies = af._split_double_text(ai_raw)
        else:
            ai_replies = [ai_raw]

        ai_reply_joined = " ".join(ai_replies)
        af.add_to_history("user", user_input)
        _log_turn("user", user_input)
        for message in ai_replies:
            af.add_to_history("ai", message)
            _log_turn("ai", message)

        with ThreadPoolExecutor() as executor:
            future_affinity = executor.submit(
                af.update_affinity,
                agent_emotion_info,
                user_input,
                ai_reply_joined,
            )
            delta, affinity_reason = future_affinity.result()

        af.record_turn(user_input, ai_reply_joined, session_break=decision.get("session_break", False))

        if delta < 0:
            af.consecutive_negative += 1
            if af.consecutive_negative >= 3:
                actual_delta = delta * 2
            else:
                actual_delta = delta
        else:
            af.consecutive_negative = 0
            actual_delta = delta

        old_affinity = af.affinity
        af.affinity = max(0, min(100, af.affinity + actual_delta))

        af.export_to_jsonl(
            user_input=user_input,
            ai_reply=ai_reply_joined,
            affinity_at_response=old_affinity,
            consecutive_neg=af.consecutive_negative,
            agent_emotion_info=agent_emotion_info,
        )

        for index, message in enumerate(ai_replies):
            if index > 0:
                time.sleep(random.uniform(0.3, 0.8))
            print(f"\nJiho: {message}")

        if decision.get("timing") == "wrap_up":
            cooldown_minutes = max(15, min(120, int(decision.get("cooldown_minutes") or 30)))
            af._cooldown_until = datetime.now() + timedelta(minutes=cooldown_minutes)
            af._cooldown_reason = decision.get("wrap_up_reason") or "had to go"
            af._last_response_time = datetime.now()
            print(f"[Cooldown] Jiho 자리비움 ~{cooldown_minutes}분 ({af._cooldown_reason})")
        else:
            af._last_response_time = datetime.now()

        multiplier_note = " (×2)" if delta < 0 and af.consecutive_negative >= 3 else ""
        timing_tag = decision.get("timing", "instant")
        action_tag = decision.get("action", "normal")
        print(f"[호감도] {old_affinity} → {af.affinity} ({delta:+d}{multiplier_note}) | {affinity_reason}")
        break_tag = decision.get("session_break", False)
        print(f"[행동] timing={timing_tag}, action={action_tag}, session_break={break_tag}")
        print(f"[Export] → {af.EXPORT_FILE}")
        print(f"[총 레이턴시: {time.time() - start_total:.4f}초]\n")


if __name__ == "__main__":
    main()
