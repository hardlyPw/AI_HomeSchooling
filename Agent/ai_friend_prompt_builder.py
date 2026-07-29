from __future__ import annotations

from collections.abc import Callable

from jiho_prompt import ROLE_DISPLAY, render_jiho_prompt


MemoryLoader = Callable[[str, int], list[dict]]
TimeContextLoader = Callable[[], tuple[str, str]]


def build_runtime_prompt(
    *,
    user_input: str,
    affinity: int,
    conversation_history: list[dict],
    memory_loader: MemoryLoader,
    time_context_loader: TimeContextLoader,
    agent_emotion_info: dict | None = None,
    long_term_memories: list[dict] | None = None,
    long_term_k: int = 5,
    decision: dict | None = None,
    time_str: str | None = None,
    time_ctx: str | None = None,
    debug_prompt: bool = False,
) -> str:
    """Prepare Jiho's final response prompt from runtime state and context."""

    long_term = (
        long_term_memories
        if long_term_memories is not None
        else memory_loader(user_input, long_term_k)
    )

    if debug_prompt:
        print_prompt_debug(
            user_input=user_input,
            agent_emotion_info=agent_emotion_info,
            long_term=long_term,
            long_term_k=long_term_k,
            conversation_history=conversation_history,
        )

    if time_str is None:
        time_str, time_ctx = time_context_loader()

    prompt = render_jiho_prompt(
        user_input=user_input,
        affinity=affinity,
        long_term_memories=long_term,
        long_term_k=long_term_k,
        conversation_history=conversation_history,
        agent_emotion_info=agent_emotion_info,
        decision=decision,
        time_str=time_str,
        time_ctx=time_ctx,
    )

    if debug_prompt:
        print(f"[4] 최종 프롬프트 (총 {len(prompt)}자):")
        print(prompt)
        print("━" * 60)

    return prompt


def print_prompt_debug(
    *,
    user_input: str,
    agent_emotion_info: dict | None,
    long_term: list[dict],
    long_term_k: int,
    conversation_history: list[dict],
) -> None:
    separator = "─" * 60
    print(f"\n{'━' * 60}")
    print("[DEBUG] 프롬프트 조립 과정")
    print(f"{'━' * 60}")
    print(f"[1] 유저 입력:\n  {user_input}")
    if agent_emotion_info:
        print(separator)
        print(f"[1-1] Agent 감정 분석: {agent_emotion_info}")
    print(separator)
    print(f"[2] 장기기억 검색 결과 (top {long_term_k}):")
    if long_term:
        for index, memory in enumerate(long_term, 1):
            description = memory["description"]
            preview = f"{description[:80]}{'...' if len(description) > 80 else ''}"
            print(f"  [{index}] (score={memory['score']}) {preview}")
    else:
        print("  (없음)")
    print(separator)
    print(f"[3] 단기기억 (최근 대화 {len(conversation_history)}개):")
    if conversation_history:
        for message in conversation_history[-6:]:
            label = ROLE_DISPLAY.get(message["role"], message["role"])
            text = message["text"]
            preview = f"{text[:60]}{'...' if len(text) > 60 else ''}"
            print(f"  {label}: {preview}")
        if len(conversation_history) > 6:
            print(f"  ... (상위 {len(conversation_history) - 6}개 생략)")
    else:
        print("  (없음)")
    print(separator)
