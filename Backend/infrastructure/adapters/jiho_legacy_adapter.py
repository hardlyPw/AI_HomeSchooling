from __future__ import annotations

from typing import Iterator

from domain.agents.base import StreamEvent
from domain.agents.conversation import (
    BaseDebuggableConversationAgent,
    ConversationAgentProfile,
    ConversationAgentState,
    ConversationBehaviorConfig,
    ConversationCapability,
)
from services.friend_service import (
    ALWAYS_COOLDOWN_PROBABILITY,
    COOLDOWN_REASONS,
    COOLDOWN_SECONDS,
    DELAY_TURN_THRESHOLD,
    EARLY_AWAY_PROBABILITY,
    LATE_AWAY_PROBABILITY,
    FriendService,
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
    delay_turn_threshold=DELAY_TURN_THRESHOLD,
    early_away_probability=EARLY_AWAY_PROBABILITY,
    late_away_probability=LATE_AWAY_PROBABILITY,
    always_cooldown_probability=ALWAYS_COOLDOWN_PROBABILITY,
    cooldown_seconds=COOLDOWN_SECONDS,
    cooldown_reasons=COOLDOWN_REASONS,
)


class JihoLegacyAdapter(BaseDebuggableConversationAgent):
    """Adapter around the existing AI_Friend-backed FriendService."""

    def __init__(self) -> None:
        self._service = FriendService()

    @property
    def profile(self) -> ConversationAgentProfile:
        return JIHO_PROFILE

    @property
    def behavior(self) -> ConversationBehaviorConfig:
        return JIHO_BEHAVIOR

    def get_state(self) -> ConversationAgentState:
        return ConversationAgentState(
            affinity=self._service.affinity,
            history=self._service.history,
            away_count=getattr(self._service, "_away_count", 0),
        )

    def reset(self) -> None:
        self._service.reset()

    def force_next_cooldown(self) -> None:
        self._service.force_next_cooldown()

    def force_next_double_text(self) -> None:
        self._service.force_next_double_text()

    def end_cooldown(self) -> None:
        self._service.end_cooldown()

    def stream_reply(self, user_message: str) -> Iterator[StreamEvent]:
        yield from self._service.stream_reply(user_message)
