"""Run the v1/v2/v3 AI_Friend demo scenarios as a repeatable suite.

Default behavior:
- Uses the real AI_Friend pipeline for retrieval, decision, prompt, generation,
  double-text splitting, and affinity update.
- Resets only in-process state between scenarios.
- Does NOT write new long-term memories unless --record-memory is passed.
- Forces v3 timing to double_text by default so the demo is reproducible.
"""

from __future__ import annotations

import argparse
import importlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Turn:
    text: str
    note: str = ""


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str
    purpose: str
    turns: tuple[Turn, ...]
    force_double_text: bool = False


SCENARIOS: dict[str, Scenario] = {
    "v1": Scenario(
        key="v1",
        title="v1 memory continuity: homework, grades, Ms. Lin",
        purpose=(
            "Shows long-term memory retrieval and a natural bridge from school "
            "stress to parent pressure to asking a teacher."
        ),
        turns=(
            Turn("ms lin's presentation is still hanging over me too", "bridge trigger"),
            Turn(
                "also systems homework is killing me again i might ask ms carter before class but that feels embarrassing",
                "systems homework / Ms. Carter",
            ),
            Turn("mom brought up grades again tonight and i just wanted ramen", "mom / grades / ramen"),
        ),
    ),
    "v2": Scenario(
        key="v2",
        title="v2 affinity shift: colder then warmer",
        purpose=(
            "Shows affinity and tone changing as the user attacks, deflects, "
            "then apologizes and asks for concrete help."
        ),
        turns=(
            Turn("systems homework is impossible again"),
            Turn("this is useless you never help", "negative toward Jiho"),
            Turn("whatever. jules ruined ms lin's project and i'm not doing it", "blame shifting"),
            Turn("you sound annoying rn", "negative toward Jiho"),
            Turn(
                "fine. my bad. i'm just stressed because my mom's gonna do that disappointed look again",
                "repair / vulnerability",
            ),
            Turn("i did waste time on discord instead of fixing the slides", "responsibility"),
            Turn("can you just help me pick one thing to do first?", "specific help request"),
            Turn("thanks. that actually helps", "positive repair"),
        ),
    ),
    "v3": Scenario(
        key="v3",
        title="v3 double-text mechanism",
        purpose=(
            "Shows that double-text is one generated response split into two "
            "message beats after the decision layer selects double_text."
        ),
        turns=(
            Turn("i hit gold in valorant and clutched a 1v4", "high-excitement trigger"),
        ),
        force_double_text=True,
    ),
}


def _load_friend_module():
    return importlib.import_module("AI_Friend")


def _reset_runtime_state(af: Any) -> None:
    if hasattr(af, "_drain_pending_chunk"):
        af._drain_pending_chunk()
    if hasattr(af, "_session_timer") and af._session_timer is not None:
        try:
            af._session_timer.cancel()
        except Exception:
            pass
        af._session_timer = None
    af.conversation_history.clear()
    af.conversation_history.extend(af.INITIAL_HISTORY)
    af.affinity = 70
    af.consecutive_negative = 0
    if hasattr(af, "_session_time_buckets_seen"):
        af._session_time_buckets_seen.clear()


def _reset_db_to_demo_seed(af: Any) -> None:
    result = af.supabase.rpc("reset_friend_memories_v2_to_demo_seed", {}).execute()
    count = result.data
    print(f"[DB reset] friend_memories_v2 restored from demo seed: {count}")


def _run_turn(
    af: Any,
    user_input: str,
    *,
    force_double_text: bool,
    record_memory: bool,
    export_jsonl: bool,
) -> dict[str, Any]:
    top_k = 1 if af.affinity <= 40 else 5
    long_term = af.get_long_term_memory(user_input, top_k) if af.USE_LONG_TERM_MEMORY else []
    time_str, time_ctx = af._consume_time_context_for_turn()

    decision = af.make_decision(user_input, long_term, time_str, time_ctx)
    natural_timing = decision.get("timing", "instant")
    if force_double_text:
        decision = dict(decision)
        decision["timing"] = "double_text"

    agent_emotion_info = {
        "emotion": decision.get("emotion", "neutral"),
        "reason": decision.get("emotion_reason", ""),
    }

    prompt = af.build_prompt(
        user_input,
        agent_emotion_info=agent_emotion_info,
        long_term_memories=long_term,
        decision=decision,
        time_str=time_str,
        time_ctx=time_ctx,
    )
    ai_raw = af.generate_ai_response(prompt)
    ai_replies = af._split_double_text(ai_raw) if decision.get("timing") == "double_text" else [ai_raw]
    ai_reply_joined = " ".join(ai_replies)

    af.add_to_history("user", user_input)
    for msg in ai_replies:
        af.add_to_history("ai", msg)

    delta, affinity_reason = af.update_affinity(agent_emotion_info, user_input, ai_reply_joined)

    if record_memory:
        af.record_turn(user_input, ai_reply_joined, session_break=decision.get("session_break", False))

    if delta < 0:
        af.consecutive_negative += 1
        actual_delta = delta * 2 if af.consecutive_negative >= 3 else delta
    else:
        af.consecutive_negative = 0
        actual_delta = delta

    old_affinity = af.affinity
    af.affinity = max(0, min(100, af.affinity + actual_delta))

    if export_jsonl:
        af.export_to_jsonl(
            user_input=user_input,
            ai_reply=ai_reply_joined,
            affinity_at_response=old_affinity,
            consecutive_neg=af.consecutive_negative,
            agent_emotion_info=agent_emotion_info,
        )

    return {
        "user": user_input,
        "retrieved_memories": long_term,
        "natural_timing": natural_timing,
        "timing": decision.get("timing", "instant"),
        "action": decision.get("action", "normal"),
        "emotion": agent_emotion_info,
        "ai_raw": ai_raw,
        "ai_replies": ai_replies,
        "affinity_before": old_affinity,
        "affinity_after": af.affinity,
        "affinity_delta": delta,
        "affinity_actual_delta": actual_delta,
        "affinity_reason": affinity_reason,
    }


def _print_turn_result(turn_no: int, result: dict[str, Any]) -> None:
    print(f"\n--- turn {turn_no} ---")
    print(f"User: {result['user']}")
    print("[retrieved]")
    for i, mem in enumerate(result["retrieved_memories"], 1):
        print(f"  {i}. score={mem.get('score')} {mem.get('description')}")
    print(
        "[decision] "
        f"timing={result['timing']} natural_timing={result['natural_timing']} "
        f"action={result['action']} emotion={result['emotion'].get('emotion')}"
    )
    for i, msg in enumerate(result["ai_replies"], 1):
        label = "Jiho" if len(result["ai_replies"]) == 1 else f"Jiho #{i}"
        print(f"{label}: {msg}")
    print(
        "[affinity] "
        f"{result['affinity_before']} -> {result['affinity_after']} "
        f"({result['affinity_actual_delta']:+d}; raw {result['affinity_delta']:+d}) "
        f"{result['affinity_reason']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run AI_Friend v1/v2/v3 demo scenarios.")
    parser.add_argument(
        "--scenario",
        choices=["all", *SCENARIOS.keys()],
        default="all",
        help="Scenario to run.",
    )
    parser.add_argument(
        "--natural-v3",
        action="store_true",
        help="Do not force v3 timing to double_text; use the natural decision result.",
    )
    parser.add_argument(
        "--record-memory",
        action="store_true",
        help="Write new session memories to friend_memories_v2. Default is read-only retrieval.",
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Call reset_friend_memories_v2_to_demo_seed before running.",
    )
    parser.add_argument(
        "--export-jsonl",
        action="store_true",
        help="Append turns to AI_Friend.EXPORT_FILE.",
    )
    parser.add_argument(
        "--save-run",
        action="store_true",
        help="Save a JSON run log under text_senarios/runs.",
    )
    args = parser.parse_args()

    af = _load_friend_module()
    af.DEBUG_PROMPT = False

    if args.reset_db:
        _reset_db_to_demo_seed(af)

    selected = list(SCENARIOS.values()) if args.scenario == "all" else [SCENARIOS[args.scenario]]
    run_log: list[dict[str, Any]] = []

    for scenario in selected:
        print("\n" + "=" * 80)
        print(f"{scenario.key}: {scenario.title}")
        print(scenario.purpose)
        print("=" * 80)
        _reset_runtime_state(af)

        scenario_results: list[dict[str, Any]] = []
        for idx, turn in enumerate(scenario.turns, 1):
            force_double = scenario.force_double_text and not args.natural_v3
            if turn.note:
                print(f"\n[note] {turn.note}")
            result = _run_turn(
                af,
                turn.text,
                force_double_text=force_double,
                record_memory=args.record_memory,
                export_jsonl=args.export_jsonl,
            )
            _print_turn_result(idx, result)
            scenario_results.append(result)

        run_log.append(
            {
                "scenario": scenario.key,
                "title": scenario.title,
                "final_affinity": af.affinity,
                "turns": scenario_results,
            }
        )

    if args.save_run:
        capstone_root = Path(__file__).resolve().parents[2]
        out_dir = capstone_root / "text_senarios" / "runs"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"senario_suite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        out_path.write_text(json.dumps(run_log, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n[run log] {out_path}")


if __name__ == "__main__":
    main()
