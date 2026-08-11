from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import math
import random
from uuid import uuid4

from domain.agents.conversation import GameSkillTier


ALLOWED_BASES = (1 / 3, 1 / 2, 2.0, 3.0)
MIN_SHIFT = -2
MAX_SHIFT = 2
MAX_ATTEMPTS = 3
ROUND_COUNT = 3
X_MIN = -4.0
X_MAX = 4.0
Y_MIN = -8.0
Y_MAX = 12.0


class QuickChat(str, Enum):
    HELLO = "hello"
    NICE = "nice"
    TRY_HARDER = "try_harder"
    GREAT_PLAY = "great_play"
    CLOSE = "close"
    GOOD_GAME = "good_game"


QUICK_CHAT_TEXT: dict[QuickChat, str] = {
    QuickChat.HELLO: "Hello!",
    QuickChat.NICE: "Nice one!",
    QuickChat.TRY_HARDER: "Step it up!",
    QuickChat.GREAT_PLAY: "Great play!",
    QuickChat.CLOSE: "So close!",
    QuickChat.GOOD_GAME: "Good game!",
}


@dataclass(frozen=True)
class GraphFunction:
    coefficient: int
    base: float
    horizontal_shift: int
    vertical_shift: int

    def __post_init__(self) -> None:
        if self.coefficient not in {-1, 1}:
            raise ValueError("Coefficient must be -1 or 1")
        if not any(math.isclose(self.base, value) for value in ALLOWED_BASES):
            raise ValueError("Base is not supported")
        if not MIN_SHIFT <= self.horizontal_shift <= MAX_SHIFT:
            raise ValueError("Horizontal shift is outside the supported range")
        if not MIN_SHIFT <= self.vertical_shift <= MAX_SHIFT:
            raise ValueError("Vertical shift is outside the supported range")

    def evaluate(self, x: float) -> float:
        return self.coefficient * self.base ** (x - self.horizontal_shift) + self.vertical_shift

    def points(self, *, step: float = 0.1) -> tuple[tuple[float, float], ...]:
        count = round((X_MAX - X_MIN) / step)
        return tuple(
            (round(x, 3), round(max(Y_MIN, min(Y_MAX, self.evaluate(x))), 4))
            for index in range(count + 1)
            for x in [X_MIN + index * step]
        )

    def to_latex(self) -> str:
        base = {
            1 / 3: r"\frac{1}{3}",
            1 / 2: r"\frac{1}{2}",
            2.0: "2",
            3.0: "3",
        }[next(value for value in ALLOWED_BASES if math.isclose(self.base, value))]
        coefficient = "-" if self.coefficient < 0 else ""
        if self.horizontal_shift > 0:
            exponent = f"x-{self.horizontal_shift}"
        elif self.horizontal_shift < 0:
            exponent = f"x+{abs(self.horizontal_shift)}"
        else:
            exponent = "x"
        if self.vertical_shift > 0:
            shift = f"+{self.vertical_shift}"
        elif self.vertical_shift < 0:
            shift = str(self.vertical_shift)
        else:
            shift = ""
        return rf"f(x)={coefficient}\left({base}\right)^{{{exponent}}}{shift}"


TARGET_CATALOG = (
    GraphFunction(1, 2.0, 1, 1),
    GraphFunction(1, 1 / 2, -1, -1),
    GraphFunction(-1, 3.0, 0, 2),
    GraphFunction(1, 1 / 3, 2, 0),
    GraphFunction(-1, 1 / 2, -2, 1),
    GraphFunction(1, 3.0, 0, -2),
)


def graph_similarity(target: GraphFunction, guess: GraphFunction) -> float:
    sample_x = tuple(X_MIN + index * 0.25 for index in range(33))
    span = Y_MAX - Y_MIN
    mean_error = sum(
        abs(
            max(Y_MIN, min(Y_MAX, target.evaluate(x)))
            - max(Y_MIN, min(Y_MAX, guess.evaluate(x)))
        )
        / span
        for x in sample_x
    ) / len(sample_x)
    return round(max(0.0, 100.0 * (1.0 - 2.5 * mean_error)), 1)


@dataclass(frozen=True)
class GameAttempt:
    function: GraphFunction
    score: float
    elapsed_ms: int


@dataclass
class GraphMatchRound:
    number: int
    target: GraphFunction
    attempts: list[GameAttempt] = field(default_factory=list)
    agent_guess: GraphFunction | None = None
    agent_score: float | None = None
    winner: str | None = None
    completed: bool = False

    @property
    def best_attempt(self) -> GameAttempt | None:
        return max(self.attempts, key=lambda item: item.score, default=None)


@dataclass(frozen=True)
class QuickChatEvent:
    sender: str
    chat: QuickChat
    text: str
    created_at: datetime


@dataclass
class GraphMatchSession:
    id: str
    user_id: str
    agent_id: str
    agent_name: str
    agent_skill: GameSkillTier
    rounds: list[GraphMatchRound]
    current_round_index: int = 0
    quick_chats: list[QuickChatEvent] = field(default_factory=list)
    completed: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        user_id: str,
        agent_id: str,
        agent_name: str,
        agent_skill: GameSkillTier,
        seed: int | None = None,
    ) -> GraphMatchSession:
        session_id = uuid4().hex
        rng = random.Random(seed if seed is not None else session_id)
        targets = rng.sample(TARGET_CATALOG, k=ROUND_COUNT)
        return cls(
            id=session_id,
            user_id=user_id,
            agent_id=agent_id,
            agent_name=agent_name,
            agent_skill=agent_skill,
            rounds=[GraphMatchRound(number=index + 1, target=target) for index, target in enumerate(targets)],
        )

    @property
    def current_round(self) -> GraphMatchRound:
        return self.rounds[self.current_round_index]

    @property
    def user_round_wins(self) -> int:
        return sum(item.winner == "user" for item in self.rounds)

    @property
    def agent_round_wins(self) -> int:
        return sum(item.winner == "agent" for item in self.rounds)


def create_agent_guess(
    target: GraphFunction,
    skill: GameSkillTier,
    *,
    seed: str,
) -> GraphFunction:
    rng = random.Random(seed)
    error_count = {
        GameSkillTier.EASY: rng.choice((2, 3)),
        GameSkillTier.NORMAL: rng.choice((1, 1, 2)),
        GameSkillTier.HARD: rng.choice((0, 0, 1)),
    }[skill]
    values: dict[str, int | float] = {
        "coefficient": target.coefficient,
        "base": target.base,
        "horizontal_shift": target.horizontal_shift,
        "vertical_shift": target.vertical_shift,
    }
    fields = rng.sample(tuple(values), k=error_count)
    for name in fields:
        if name == "coefficient":
            values[name] = -target.coefficient
        elif name == "base":
            values[name] = rng.choice(tuple(value for value in ALLOWED_BASES if not math.isclose(value, target.base)))
        else:
            current = int(values[name])
            values[name] = rng.choice(tuple(value for value in range(MIN_SHIFT, MAX_SHIFT + 1) if value != current))
    return GraphFunction(**values)
