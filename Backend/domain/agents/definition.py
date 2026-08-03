from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar


class AgentType(str, Enum):
    """Content category that determines which agent contract is used."""

    CONVERSATION = "conversation"
    LESSON = "lesson"
    PROBLEM_SOLVER = "problem_solver"


ProfileT = TypeVar("ProfileT")
BehaviorT = TypeVar("BehaviorT")
RuntimeT = TypeVar("RuntimeT")


@dataclass(frozen=True)
class AgentDefinition(Generic[ProfileT, BehaviorT, RuntimeT]):
    """Immutable configuration required to construct one type of agent."""

    agent_type: AgentType
    profile: ProfileT
    behavior: BehaviorT
    runtime: RuntimeT
