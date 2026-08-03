from __future__ import annotations

from collections.abc import Callable
import re
from uuid import uuid4

from domain.agents.conversation import (
    ConversationAgentDefinition,
    ConversationAgentProfile,
    ConversationCapability,
)
from domain.agents.conversation_creation import (
    ConversationAgentDesigner,
    ConversationAgentQuestionnaire,
    GeneratedConversationAgentDesign,
)
from domain.agents.conversation_defaults import DEFAULT_CONVERSATION_RUNTIME
from domain.agents.conversation_presets import ConversationPresetResolver
from domain.agents.definition import AgentDefinition, AgentType


GENERATED_AGENT_CAPABILITIES = frozenset(
    {
        ConversationCapability.AFFINITY,
        ConversationCapability.LONG_TERM_MEMORY,
        ConversationCapability.DELAYED_REPLY,
        ConversationCapability.COOLDOWN,
        ConversationCapability.DOUBLE_TEXT,
    }
)


class ConversationAgentCreationService:
    """Builds a validated AgentDefinition from user answers and LLM design."""

    def __init__(
        self,
        designer: ConversationAgentDesigner,
        *,
        preset_resolver: ConversationPresetResolver | None = None,
        id_factory: Callable[[str], str] | None = None,
    ) -> None:
        self._designer = designer
        self._preset_resolver = preset_resolver or ConversationPresetResolver()
        self._id_factory = id_factory or self._default_id_factory

    def create(
        self,
        questionnaire: ConversationAgentQuestionnaire,
    ) -> ConversationAgentDefinition:
        design = self._designer.design(questionnaire)
        self._validate_design(design)

        behavior = self._preset_resolver.resolve_behavior(
            design.behavior_selection,
            cooldown_reasons=design.cooldown_reasons,
        )
        initial_affinity = self._preset_resolver.resolve_initial_affinity(
            design.behavior_selection
        )
        profile = ConversationAgentProfile(
            agent_id=self._id_factory(design.display_name),
            display_name=design.display_name.strip(),
            description=design.description.strip(),
            persona=design.persona,
            initial_affinity=initial_affinity,
            capabilities=GENERATED_AGENT_CAPABILITIES,
        )
        return AgentDefinition(
            agent_type=AgentType.CONVERSATION,
            profile=profile,
            behavior=behavior,
            runtime=DEFAULT_CONVERSATION_RUNTIME,
        )

    @staticmethod
    def _validate_design(design: GeneratedConversationAgentDesign) -> None:
        required_text = {
            "display_name": design.display_name,
            "description": design.description,
            "persona narrative": design.persona.narrative,
            "user profile": design.persona.user_profile,
            "decision guidance": design.persona.decision_guidance,
            "affinity rubric": design.persona.affinity_rubric,
        }
        missing = [name for name, value in required_text.items() if not value.strip()]
        if missing:
            raise ValueError(f"Agent design is missing: {', '.join(missing)}")
        if len(design.persona.affinity_stage_directions) != 4:
            raise ValueError("Exactly four affinity stage directions are required")
        if not all(item.strip() for item in design.persona.affinity_stage_directions):
            raise ValueError("Affinity stage directions cannot be blank")
        if not design.persona.behavior_bans:
            raise ValueError("At least one character behavior ban is required")
        if not design.cooldown_reasons:
            raise ValueError("At least one cooldown reason is required")

    @staticmethod
    def _default_id_factory(display_name: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
        return f"{slug or 'friend'}-{uuid4().hex[:8]}"
