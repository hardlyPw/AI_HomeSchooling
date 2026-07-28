from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import random
from typing import Callable, Iterator

from domain.agents.base import BaseAgent, StreamEvent


class ConversationCapability(str, Enum):
    """Feature flags supported by a conversation agent."""

    AFFINITY = "affinity"
    LONG_TERM_MEMORY = "long_term_memory"
    DELAYED_REPLY = "delayed_reply"
    COOLDOWN = "cooldown"
    DOUBLE_TEXT = "double_text"
    DEBUG_CONTROLS = "debug_controls"


class AvailabilityMode(str, Enum):
    """Current response availability for a conversation agent."""

    NORMAL = "normal"
    DELAYED = "delayed"
    COOLDOWN = "cooldown"


@dataclass(frozen=True)
class ConversationAgentProfile:
    """Static identity and persona data shared by friend-style agents."""

    agent_id: str
    display_name: str
    description: str
    persona: str
    initial_affinity: int
    affinity_min: int = 0
    affinity_max: int = 100
    capabilities: frozenset[ConversationCapability] = field(default_factory=frozenset)


@dataclass(frozen=True)
class ConversationBehaviorConfig:
    """Timing and relationship policies that vary by conversation agent."""

    delay_turn_threshold: int
    early_away_probability: float
    late_away_probability: float
    always_cooldown_probability: float
    cooldown_seconds: int
    cooldown_reasons: tuple[str, ...]
    initial_delayed_reply_seconds: int = 30
    extended_delayed_reply_seconds: int = 60
    double_text_probability: float = 0.0
    affinity_positive_step: int = 1
    affinity_negative_step: int = -1
    affinity_negative_streak_threshold: int = 3
    affinity_negative_streak_multiplier: int = 2


@dataclass(frozen=True)
class ConversationAgentState:
    """Runtime state that the UI or application layer can inspect."""

    affinity: int
    history: list[dict]
    availability_mode: AvailabilityMode = AvailabilityMode.NORMAL
    away_count: int = 0


class BaseConversationAgent(BaseAgent):
    """Base class for free-form character conversation agents."""

    @property
    @abstractmethod
    def profile(self) -> ConversationAgentProfile:
        raise NotImplementedError

    @property
    @abstractmethod
    def behavior(self) -> ConversationBehaviorConfig:
        raise NotImplementedError

    @property
    def agent_id(self) -> str:
        return self.profile.agent_id

    @property
    def display_name(self) -> str:
        return self.profile.display_name

    @property
    def affinity(self) -> int:
        return self.get_state().affinity

    @property
    def history(self) -> list[dict]:
        return self.get_state().history

    @abstractmethod
    def get_state(self) -> ConversationAgentState:
        raise NotImplementedError

    @abstractmethod
    def stream_reply(self, user_message: str) -> Iterator[StreamEvent]:
        raise NotImplementedError

    def clamp_affinity(self, value: int) -> int:
        return max(self.profile.affinity_min, min(self.profile.affinity_max, value))

    def get_affinity_delta(self, base_delta: int, negative_streak: int = 0) -> int:
        if base_delta < 0 and negative_streak >= self.behavior.affinity_negative_streak_threshold:
            return base_delta * self.behavior.affinity_negative_streak_multiplier
        return base_delta

    def away_probability_for_turn(self, turn_count: int) -> float:
        if turn_count < self.behavior.delay_turn_threshold:
            return self.behavior.early_away_probability
        return self.behavior.late_away_probability

    def should_enter_cooldown(self, random_value: Callable[[], float] = random.random) -> bool:
        return random_value() < self.behavior.always_cooldown_probability

    def should_consider_away(
        self,
        turn_count: int,
        random_value: Callable[[], float] = random.random,
    ) -> bool:
        return random_value() < self.away_probability_for_turn(turn_count)

    def should_double_text(self, random_value: Callable[[], float] = random.random) -> bool:
        return random_value() < self.behavior.double_text_probability

    def pick_cooldown_reason(
        self,
        chooser: Callable[[tuple[str, ...]], str] = random.choice,
    ) -> str:
        return chooser(self.behavior.cooldown_reasons)


class BaseDebuggableConversationAgent(BaseConversationAgent):
    """Optional debug controls for character agents used by developer UI."""

    @abstractmethod
    def force_next_cooldown(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def force_next_double_text(self) -> None:
        raise NotImplementedError

    @abstractmethod
    def end_cooldown(self) -> None:
        raise NotImplementedError
