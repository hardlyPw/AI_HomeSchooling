from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, TypeAlias


class FriendEvent(Protocol):
    def to_payload(self) -> dict[str, Any]:
        raise NotImplementedError


@dataclass(frozen=True)
class FriendStatusEvent:
    status: str
    wait_seconds: int

    def to_payload(self) -> dict[str, Any]:
        return {"status": self.status, "wait_seconds": self.wait_seconds}


@dataclass(frozen=True)
class FriendDecisionEvent:
    decision: dict[str, Any]

    def to_payload(self) -> dict[str, Any]:
        return {"decision": self.decision}


@dataclass(frozen=True)
class FriendDeltaEvent:
    delta: str

    def to_payload(self) -> dict[str, Any]:
        return {"delta": self.delta}


@dataclass(frozen=True)
class FriendMessageBreakEvent:
    def to_payload(self) -> dict[str, Any]:
        return {"message_break": True}


@dataclass(frozen=True)
class FriendTimingEvent:
    total_seconds: float

    def to_payload(self) -> dict[str, Any]:
        return {"timing": {"total_seconds": self.total_seconds}}


@dataclass(frozen=True)
class FriendTokenUsageEvent:
    decision_prompt: int | None
    decision_completion: int | None
    reply_prompt: int | None
    reply_completion: int | None

    def to_payload(self) -> dict[str, Any]:
        components = [
            (self.decision_prompt or 0) + (self.decision_completion or 0),
            (self.reply_prompt or 0) + (self.reply_completion or 0),
        ]
        return {
            "tokens": {
                "decision_prompt": self.decision_prompt,
                "decision_completion": self.decision_completion,
                "reply_prompt": self.reply_prompt,
                "reply_completion": self.reply_completion,
                "total": sum(components) if any(components) else None,
            }
        }


@dataclass(frozen=True)
class FriendAffinityEvent:
    affinity: int
    affinity_prev: int

    def to_payload(self) -> dict[str, Any]:
        return {
            "affinity": self.affinity,
            "affinity_prev": self.affinity_prev,
        }


@dataclass(frozen=True)
class FriendDoneEvent:
    def to_payload(self) -> dict[str, Any]:
        return {"done": True}


FriendStreamEvent: TypeAlias = (
    FriendStatusEvent
    | FriendDecisionEvent
    | FriendDeltaEvent
    | FriendMessageBreakEvent
    | FriendTimingEvent
    | FriendTokenUsageEvent
    | FriendAffinityEvent
    | FriendDoneEvent
)
