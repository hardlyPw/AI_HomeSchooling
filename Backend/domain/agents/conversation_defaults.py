from __future__ import annotations

from domain.agents.conversation import (
    ConversationMemoryConfig,
    ConversationPromptConfig,
    ConversationRuntimeConfig,
    ModelInvocationConfig,
)
from domain.agents.conversation_safety import CONVERSATION_SYSTEM_SAFETY_RULES


DEFAULT_CONVERSATION_RUNTIME = ConversationRuntimeConfig(
    response_model=ModelInvocationConfig(
        model="gpt-4o",
        temperature=0.8,
        max_tokens=300,
    ),
    decision_model=ModelInvocationConfig(
        model="gpt-4o-mini",
        temperature=0.6,
        max_tokens=200,
    ),
    memory=ConversationMemoryConfig(
        enabled=True,
        table_name="friend_memories_v2",
        match_rpc_name="match_friend_memories_v2",
        reset_rpc_name="reset_friend_memories_v2_to_demo_seed",
        embedding_model="sentence-transformers/all-MiniLM-L6-v2",
        session_timeout_seconds=5 * 60,
        low_affinity_top_k=1,
        normal_top_k=5,
        top_k_affinity_cutoff=40,
        extraction_model=ModelInvocationConfig(
            model="gpt-4o-mini",
            temperature=0,
            max_tokens=1200,
        ),
    ),
    prompt=ConversationPromptConfig(
        response_history_limit=20,
        decision_history_limit=8,
        affinity_stage_maxima=(30, 49, 69),
        affinity_delta_min=-10,
        affinity_delta_max=10,
    ),
    system_safety_rules=CONVERSATION_SYSTEM_SAFETY_RULES,
)
