from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.agents.conversation import ConversationPersonaConfig
from domain.agents.conversation_presets import ConversationBehaviorSelection


@dataclass(frozen=True)
class ConversationAgentQuestionnaire:
    """User-authored answers collected by the Add Agent flow."""

    requested_name: str
    relationship: str
    personality: str
    speech_style: str
    interests: str
    reaction_style: str = ""
    background: str = ""
    avoidances: str = ""
    dialogue_examples: str = ""
    additional_description: str = ""


@dataclass(frozen=True)
class GeneratedConversationAgentDesign:
    """Structured, non-numeric result returned by the Agent-design LLM."""

    display_name: str
    description: str
    persona: ConversationPersonaConfig
    behavior_selection: ConversationBehaviorSelection
    cooldown_reasons: tuple[str, ...]


class ConversationAgentDesigner(Protocol):
    def design(
        self,
        questionnaire: ConversationAgentQuestionnaire,
    ) -> GeneratedConversationAgentDesign:
        """Convert questionnaire answers into constrained Agent material."""
        ...
