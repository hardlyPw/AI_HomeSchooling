from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import random
from uuid import uuid4

from domain.agents.conversation import GameSkillTier


CARD_COUNT = 36
PAIR_COUNT = CARD_COUNT // 2
PREVIEW_SECONDS = 10
TURN_SECONDS = 15


@dataclass(frozen=True)
class AgentCardTurn:
    indices: tuple[int, int]
    values: tuple[int, int]
    matched: bool
    score_after: int


@dataclass
class MemoryMatchSession:
    id: str
    user_id: str
    player_name: str
    agent_id: str
    agent_name: str
    agent_skill: GameSkillTier
    board: tuple[int, ...]
    matched_indices: set[int] = field(default_factory=set)
    agent_seen: dict[int, int] = field(default_factory=dict)
    user_score: int = 0
    agent_score: int = 0
    phase: str = "preview"
    last_agent_turns: tuple[AgentCardTurn, ...] = ()
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        player_name: str,
        agent_id: str,
        agent_name: str,
        agent_skill: GameSkillTier,
        seed: int | str | None = None,
    ) -> MemoryMatchSession:
        session_id = uuid4().hex
        rng = random.Random(seed if seed is not None else session_id)
        cards = list(range(1, PAIR_COUNT + 1)) * 2
        rng.shuffle(cards)
        retention = {
            GameSkillTier.EASY: 6,
            GameSkillTier.NORMAL: 14,
            GameSkillTier.HARD: 24,
        }[agent_skill]
        remembered = rng.sample(range(CARD_COUNT), k=retention)
        return cls(
            id=session_id,
            user_id=user_id,
            player_name=player_name,
            agent_id=agent_id,
            agent_name=agent_name,
            agent_skill=agent_skill,
            board=tuple(cards),
            agent_seen={index: cards[index] for index in remembered},
        )

    @property
    def completed(self) -> bool:
        return len(self.matched_indices) == CARD_COUNT

    @property
    def winner(self) -> str | None:
        if not self.completed:
            return None
        if self.user_score > self.agent_score:
            return "user"
        if self.agent_score > self.user_score:
            return "agent"
        return "draw"
