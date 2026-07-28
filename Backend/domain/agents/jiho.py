from __future__ import annotations

from domain.agents.conversation import (
    ConversationAgentProfile,
    ConversationBehaviorConfig,
    ConversationCapability,
)


JIHO_PROFILE = ConversationAgentProfile(
    agent_id="jiho",
    display_name="Jiho",
    description="A casual middle-school friend who chats naturally with the learner.",
    persona=(
        "Jiho is a same-age friend character for everyday conversation. "
        "He answers casually, remembers relationship context, and reacts through affinity."
    ),
    initial_affinity=70,
    capabilities=frozenset(
        {
            ConversationCapability.AFFINITY,
            ConversationCapability.LONG_TERM_MEMORY,
            ConversationCapability.DELAYED_REPLY,
            ConversationCapability.COOLDOWN,
            ConversationCapability.DOUBLE_TEXT,
            ConversationCapability.DEBUG_CONTROLS,
        }
    ),
)

JIHO_BEHAVIOR = ConversationBehaviorConfig(
    delay_turn_threshold=50,
    early_away_probability=0.01,
    late_away_probability=0.10,
    always_cooldown_probability=0.001,
    cooldown_seconds=5 * 60,
    cooldown_reasons=(
        "in a game",
        "eating",
        "watching yt",
        "in the shower",
        "looking for my charger",
    ),
)
