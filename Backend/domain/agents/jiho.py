from __future__ import annotations

from domain.agents.conversation import (
    ConversationAgentDefinition,
    ConversationAgentProfile,
    ConversationBehaviorConfig,
    ConversationCapability,
    ConversationPersonaConfig,
    GameSkillTier,
)
from domain.agents.conversation_defaults import DEFAULT_CONVERSATION_RUNTIME
from domain.agents.conversation_presets import (
    AffinitySensitivityLevel,
    AvailabilityLevel,
    ConversationBehaviorSelection,
    ConversationPresetResolver,
    CooldownLevel,
    DoubleTextLevel,
    InitialClosenessLevel,
    ReplyDelayLevel,
)
from domain.agents.definition import AgentDefinition, AgentType
from domain.agents.jiho_persona import (
    JIHO_AFFINITY_RUBRIC,
    JIHO_AFFINITY_STAGE_DIRECTIONS,
    JIHO_BEHAVIOR_BANS,
    JIHO_DECISION_GUIDANCE,
    JIHO_PERSONA,
    JIHO_USER_PROFILE,
)


JIHO_PROFILE = ConversationAgentProfile(
    agent_id="jiho",
    display_name="Jiho",
    description="A casual middle-school friend who chats naturally with the learner.",
    persona=ConversationPersonaConfig(
        narrative=JIHO_PERSONA,
        user_profile=JIHO_USER_PROFILE,
        decision_guidance=JIHO_DECISION_GUIDANCE,
        affinity_rubric=JIHO_AFFINITY_RUBRIC,
        affinity_stage_directions=JIHO_AFFINITY_STAGE_DIRECTIONS,
        behavior_bans=JIHO_BEHAVIOR_BANS,
    ),
    initial_affinity=70,
    game_skill_tier=GameSkillTier.NORMAL,
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

JIHO_BEHAVIOR_SELECTION = ConversationBehaviorSelection(
    availability=AvailabilityLevel.INDEPENDENT,
    reply_delay=ReplyDelayLevel.STANDARD,
    cooldown=CooldownLevel.RARE,
    double_text=DoubleTextLevel.NEVER,
    affinity_sensitivity=AffinitySensitivityLevel.BALANCED,
    initial_closeness=InitialClosenessLevel.FRIEND,
)

JIHO_COOLDOWN_REASONS = (
    "in a game",
    "eating",
    "watching yt",
    "in the shower",
    "looking for my charger",
)

JIHO_BEHAVIOR: ConversationBehaviorConfig = ConversationPresetResolver().resolve_behavior(
    JIHO_BEHAVIOR_SELECTION,
    cooldown_reasons=JIHO_COOLDOWN_REASONS,
)

JIHO_DEFINITION: ConversationAgentDefinition = AgentDefinition(
    agent_type=AgentType.CONVERSATION,
    profile=JIHO_PROFILE,
    behavior=JIHO_BEHAVIOR,
    runtime=DEFAULT_CONVERSATION_RUNTIME,
)
