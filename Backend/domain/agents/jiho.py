from __future__ import annotations

import sys
from pathlib import Path

from domain.agents.conversation import (
    ConversationAgentProfile,
    ConversationBehaviorConfig,
    ConversationCapability,
)

_AGENT_DIR = Path(__file__).resolve().parents[3] / "Agent"
if str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))

from jiho_prompt import AI_PERSONA  # noqa: E402


JIHO_PROFILE = ConversationAgentProfile(
    agent_id="jiho",
    display_name="Jiho",
    description="A casual middle-school friend who chats naturally with the learner.",
    persona=AI_PERSONA,
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
