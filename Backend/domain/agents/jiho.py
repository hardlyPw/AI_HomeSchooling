from __future__ import annotations

from domain.agents.conversation import (
    ConversationAgentProfile,
    ConversationBehaviorConfig,
    ConversationCapability,
)
from domain.agents.jiho_persona import JIHO_PERSONA


JIHO_PROFILE = ConversationAgentProfile(
    agent_id="jiho",
    display_name="Jiho",
    description="A casual middle-school friend who chats naturally with the learner.",
    persona=JIHO_PERSONA,
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
