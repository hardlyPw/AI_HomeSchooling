from __future__ import annotations

from dataclasses import dataclass
import random
from typing import Callable

from domain.agents.conversation import AvailabilityMode, ConversationBehaviorConfig


@dataclass(frozen=True)
class AwayDecision:
    """Decision for whether the agent replies now, later, or after cooldown."""

    mode: AvailabilityMode = AvailabilityMode.NORMAL
    wait_seconds: int = 0
    reason: str = ""


@dataclass(frozen=True)
class TimingPolicyResult:
    """Timing decision plus the updated counters consumed by the service."""

    decision: AwayDecision
    away_count: int
    consumed_forced_cooldown: bool = False


class ConversationTimingPolicy:
    """Decides delayed replies and cooldown behavior from agent config."""

    def __init__(self, behavior: ConversationBehaviorConfig) -> None:
        self._behavior = behavior

    def pick_away_decision(
        self,
        *,
        turn_count: int,
        away_count: int,
        force_cooldown: bool = False,
        random_value: Callable[[], float] = random.random,
        choose_reason: Callable[[tuple[str, ...]], str] = random.choice,
    ) -> TimingPolicyResult:
        if force_cooldown:
            decision, next_away_count = self._begin_cooldown(away_count, choose_reason)
            return TimingPolicyResult(
                decision=decision,
                away_count=next_away_count,
                consumed_forced_cooldown=True,
            )

        if random_value() < self._behavior.always_cooldown_probability:
            decision, next_away_count = self._begin_cooldown(away_count, choose_reason)
            return TimingPolicyResult(decision=decision, away_count=next_away_count)

        if random_value() >= self._away_probability_for_turn(turn_count):
            return TimingPolicyResult(
                decision=AwayDecision(),
                away_count=away_count,
            )

        next_away_count = away_count + 1
        if next_away_count <= 3:
            return TimingPolicyResult(
                decision=AwayDecision(
                    mode=AvailabilityMode.DELAYED,
                    wait_seconds=self._behavior.initial_delayed_reply_seconds,
                ),
                away_count=next_away_count,
            )
        if next_away_count == 4:
            return TimingPolicyResult(
                decision=AwayDecision(
                    mode=AvailabilityMode.DELAYED,
                    wait_seconds=self._behavior.extended_delayed_reply_seconds,
                ),
                away_count=next_away_count,
            )

        decision, cooldown_away_count = self._begin_cooldown(next_away_count, choose_reason)
        return TimingPolicyResult(decision=decision, away_count=cooldown_away_count)

    def _away_probability_for_turn(self, turn_count: int) -> float:
        if turn_count < self._behavior.delay_turn_threshold:
            return self._behavior.early_away_probability
        return self._behavior.late_away_probability

    def _begin_cooldown(
        self,
        away_count: int,
        choose_reason: Callable[[tuple[str, ...]], str],
    ) -> tuple[AwayDecision, int]:
        next_away_count = away_count + 1
        return (
            AwayDecision(
                mode=AvailabilityMode.COOLDOWN,
                wait_seconds=self._behavior.cooldown_seconds,
                reason=choose_reason(self._behavior.cooldown_reasons),
            ),
            next_away_count,
        )


@dataclass(frozen=True)
class AffinityPolicyResult:
    """Affinity update result for one conversation turn."""

    previous_affinity: int
    next_affinity: int
    actual_delta: int
    consecutive_negative: int


class AffinityPolicy:
    """Applies affinity deltas while enforcing bounds and negative streak rules."""

    def __init__(self, behavior: ConversationBehaviorConfig) -> None:
        self._behavior = behavior

    def apply_delta(
        self,
        *,
        current_affinity: int,
        delta: int,
        consecutive_negative: int,
        affinity_min: int = 0,
        affinity_max: int = 100,
    ) -> AffinityPolicyResult:
        next_negative_streak = consecutive_negative
        adjusted_delta = delta
        if delta < 0:
            next_negative_streak += 1
            if next_negative_streak >= self._behavior.affinity_negative_streak_threshold:
                adjusted_delta *= self._behavior.affinity_negative_streak_multiplier
        else:
            next_negative_streak = 0

        next_affinity = max(affinity_min, min(affinity_max, current_affinity + adjusted_delta))
        return AffinityPolicyResult(
            previous_affinity=current_affinity,
            next_affinity=next_affinity,
            actual_delta=next_affinity - current_affinity,
            consecutive_negative=next_negative_streak,
        )
