from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from domain.agents.conversation import ConversationBehaviorConfig


class AvailabilityLevel(str, Enum):
    ENGAGED = "engaged"
    BALANCED = "balanced"
    INDEPENDENT = "independent"


class ReplyDelayLevel(str, Enum):
    SHORT = "short"
    STANDARD = "standard"
    LONG = "long"


class CooldownLevel(str, Enum):
    RARE = "rare"
    OCCASIONAL = "occasional"
    FREQUENT = "frequent"


class DoubleTextLevel(str, Enum):
    NEVER = "never"
    OCCASIONAL = "occasional"
    FREQUENT = "frequent"


class AffinitySensitivityLevel(str, Enum):
    STEADY = "steady"
    BALANCED = "balanced"
    REACTIVE = "reactive"


class InitialClosenessLevel(str, Enum):
    NEW = "new"
    ACQUAINTED = "acquainted"
    FRIEND = "friend"
    CLOSE = "close"


@dataclass(frozen=True)
class ConversationBehaviorSelection:
    """Constrained semantic values selected by the Agent-design LLM."""

    availability: AvailabilityLevel
    reply_delay: ReplyDelayLevel
    cooldown: CooldownLevel
    double_text: DoubleTextLevel
    affinity_sensitivity: AffinitySensitivityLevel
    initial_closeness: InitialClosenessLevel


_AVAILABILITY_PRESETS = {
    AvailabilityLevel.ENGAGED: (80, 0.0, 0.03),
    AvailabilityLevel.BALANCED: (60, 0.01, 0.07),
    AvailabilityLevel.INDEPENDENT: (50, 0.01, 0.10),
}

_REPLY_DELAY_PRESETS = {
    ReplyDelayLevel.SHORT: (10, 30),
    ReplyDelayLevel.STANDARD: (30, 60),
    ReplyDelayLevel.LONG: (60, 120),
}

_COOLDOWN_PRESETS = {
    CooldownLevel.RARE: (0.001, 5 * 60),
    CooldownLevel.OCCASIONAL: (0.005, 10 * 60),
    CooldownLevel.FREQUENT: (0.015, 15 * 60),
}

_DOUBLE_TEXT_PRESETS = {
    DoubleTextLevel.NEVER: 0.0,
    DoubleTextLevel.OCCASIONAL: 0.10,
    DoubleTextLevel.FREQUENT: 0.25,
}

_AFFINITY_PRESETS = {
    AffinitySensitivityLevel.STEADY: (1, -1, 4, 1),
    AffinitySensitivityLevel.BALANCED: (1, -1, 3, 2),
    AffinitySensitivityLevel.REACTIVE: (2, -2, 2, 2),
}

_INITIAL_AFFINITY_PRESETS = {
    InitialClosenessLevel.NEW: 30,
    InitialClosenessLevel.ACQUAINTED: 50,
    InitialClosenessLevel.FRIEND: 70,
    InitialClosenessLevel.CLOSE: 85,
}


class ConversationPresetResolver:
    """Maps constrained LLM selections to validated system-owned numbers."""

    def resolve_behavior(
        self,
        selection: ConversationBehaviorSelection,
        *,
        cooldown_reasons: tuple[str, ...],
    ) -> ConversationBehaviorConfig:
        if not cooldown_reasons:
            raise ValueError("At least one cooldown reason is required")

        delay_threshold, early_away, late_away = _AVAILABILITY_PRESETS[
            selection.availability
        ]
        initial_delay, extended_delay = _REPLY_DELAY_PRESETS[selection.reply_delay]
        cooldown_probability, cooldown_seconds = _COOLDOWN_PRESETS[selection.cooldown]
        positive_step, negative_step, streak_threshold, streak_multiplier = (
            _AFFINITY_PRESETS[selection.affinity_sensitivity]
        )

        return ConversationBehaviorConfig(
            delay_turn_threshold=delay_threshold,
            early_away_probability=early_away,
            late_away_probability=late_away,
            always_cooldown_probability=cooldown_probability,
            cooldown_seconds=cooldown_seconds,
            cooldown_reasons=cooldown_reasons,
            initial_delayed_reply_seconds=initial_delay,
            extended_delayed_reply_seconds=extended_delay,
            double_text_probability=_DOUBLE_TEXT_PRESETS[selection.double_text],
            affinity_positive_step=positive_step,
            affinity_negative_step=negative_step,
            affinity_negative_streak_threshold=streak_threshold,
            affinity_negative_streak_multiplier=streak_multiplier,
        )

    def resolve_initial_affinity(
        self,
        selection: ConversationBehaviorSelection,
    ) -> int:
        return _INITIAL_AFFINITY_PRESETS[selection.initial_closeness]
